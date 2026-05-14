# Story S3-03 — `_yarn` lockfile parser + ADR-0003 finalization

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready (HARDENED)
**Effort:** L
**Depends on:** S3-01 (`_pnpm.py` + inert `_lockfiles/__init__.py`), S3-02 (`_npm.py` + reinforced inert-`__init__` invariant), S1-01 (Phase 1 marker exceptions), the `parsers/_io.open_capped` primitive already on disk from S1-02/S1-03
**ADRs honored:** ADR-0003 (`pyarn` if maintained, else hand-rolled — **finalized in this PR**), ADR-0007 (`WarningId` constructed at catch site), ADR-0008 (in-process caps via the shared `open_capped` kernel), ADR-0009 (`pyarn` is the single Phase 1 conditional dep)
**Phase-0 invariant honored:** `tests/unit/test_errors.py::test_subclasses_are_markers_only` and `::test_phase1_subclasses_accept_message_arg_and_expose_args0` — marker exceptions accept a single positional message string and expose **no** instance state.

## Validation notes (2026-05-14 — phase-story-validator HARDENED)

**Four block-level corrections** applied (see `_validation/S3-03-yarn-lockfile-parser.md` for the full audit):

1. **Marker exception construction.** The draft prescribed `MalformedLockfileError(path=path, cause=e)` (kwargs) and a test assertion `exc.value.path == lockfile`. Phase 0's `test_subclasses_are_markers_only` and S1-01's `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize **every Phase-1 marker** (incl. `MalformedLockfileError`) as positional-only — `hasattr(exc, "path")` is an asserted **negative**. Construction must be `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause`. Same defect S1-02 / S1-03 / S3-01 / S3-02 hardenings already corrected.
2. **Shared `open_capped` kernel.** The draft prescribed an in-module `_open_with_size_check(path, max_bytes)` reimplementing `O_NOFOLLOW` + `os.fstat` size-cap from scratch — including raw `e.errno in (40, 62)` instead of `errno.ELOOP`. That kernel **already exists** on disk at `src/codegenie/parsers/_io.open_capped`, with the registry-pattern hook (`parser_kind: str` discriminator). Its docstring names exactly this case: "adding a future `safe_toml` is a new caller of this primitive with a new `parser_kind` literal — zero edits here." Reimplementing it duplicates load-bearing security code, defeats the structured `probe.parser.cap_exceeded` event's `parser_kind` discriminator, and violates CLAUDE.md "Extension by addition." `_yarn.py` must call `open_capped(path, max_bytes=YARN_LOCKFILE_MAX_BYTES, parser_kind="yarn_lockfile")`.
3. **No edit to `_lockfiles/__init__.py`.** Draft Implementation-outline step 8 prescribed "Update `src/codegenie/probes/_lockfiles/__init__.py` with the `YarnLock` re-export (additive)." That contradicts S3-01's settled inert form (`__all__: list[str] = []`) and S3-02's AC-1 (non-edit pinned by `test_lockfiles_init_remains_inert`). Consumers import siblings directly. S3-03 inherits and adds **two** new files only: `_yarn.py` and the ADR-0003 land-time-selection edit.
4. **Rule-of-three resolution — defer extraction with recorded rationale.** S3-01 and S3-02 explicitly punted the shared `_translate(path, *, cause)` helper to S3-03's land time. Decision pinned in Notes for the implementer (DP-1): **DEFER**. Yarn's dispatch is structurally different from pnpm/npm — it catches `(SizeCapExceeded, SymlinkRefusedError)` to passthrough plus `Exception` to translate (the hand-rolled scanner raises `ValueError` and `UnicodeDecodeError`; `pyarn` may raise its own classes), and the pre-parse step is `open_capped(...)` rather than `safe_yaml.load(...)` / `safe_json.load(...)`. The trio is two-of-a-kind (pnpm/npm) plus one-of-a-kind (yarn); extracting `_translate` would either (a) widen the helper to swallow `Exception` (loosening pnpm/npm's `MalformedYAMLError` / `MalformedJSONError` narrow catch) or (b) require two helpers, defeating the point. CLAUDE.md Rule 2: "three similar lines is better than premature abstraction." Documented; no helper extracted here. Phase 2 can revisit if a fourth lockfile (`bun.lockb`) reveals the right shape.

**Fourteen harden-tier additions** mirror S3-01/S3-02's hardened shape with yarn-specific deltas:

1. Explicit AC for the `__cause__` chain (`isinstance(exc.__cause__, BaseException)` and the cause's `type(...).__name__` appears in `exc.args[0]`).
2. Explicit AC for `str(path) in exc.args[0]` (downstream `WarningId` recovery per ADR-0007).
3. Parametrized markers-only-negative test pinning `not hasattr(exc, "path" | "cap" | "detail" | "cause" | "warning_id")`.
4. Size-cap test rewritten to monkey-patch `os.fstat`, avoiding the 60 MB write the draft prescribed (Rule 2 — smallest test that proves the contract; mirrors S3-01/S3-02 precedents).
5. Symlink-passthrough test added (`SymlinkRefusedError` re-raise from `open_capped`).
6. Both dispatch paths (`_HAS_PYARN=True`, `_HAS_PYARN=False`) tested via `monkeypatch.setattr(_yarn, "_HAS_PYARN", ...)`; the malformed-bytes test runs only on the hand-rolled path (forced via monkeypatch) so the assertion is deterministic regardless of `pyarn`'s local install state.
7. `_HAS_PYARN` semantics pinned: `_HAS_PYARN == (importlib.util.find_spec("pyarn") is not None)`; tested with two monkey-patches of `importlib.util.find_spec`.
8. `YarnLock` / `YarnLockEntry` declared `total=False`; module exports `__all__ = ["YarnLock", "YarnLockEntry", "parse"]`.
9. Module constants typed `Final[int]`.
10. Architectural test `test_yarn_module_does_not_reference_sibling_parsers` pinning CLAUDE.md "Extension by addition" (adding `_bun.py` later requires zero edits to `_yarn.py`).
11. Architectural test `test_lockfiles_init_remains_inert` re-asserted at S3-03 land — S3-03 must not touch the family-`__init__`.
12. `parser_kind="yarn_lockfile"` literal pinned at module scope and asserted in a structured-event capture test (`probe.parser.cap_exceeded` event surfaces this discriminator — the registry pattern's payoff).
13. `pyarn` API surface verified at land-time: AC-13 requires the implementer to verify the actual `pyarn` import shape (modern `pyarn` exposes `pyarn.lockfile.Lockfile.from_file(path)`, **not** `pyarn.parse(...)`) and adjust the dispatch call accordingly; the Green code below shows the most likely shape with a fallback note.
14. Local-fuzz AC tightened: the throwaway fuzz script lives at `tools/fuzz_yarn_lock.py` (committed to `tools/`, not `tests/`, so it isn't pytest-collected); PR body must paste its summary line.

**Design-pattern findings recorded:**

- **DP-1 (rule of three — defer extraction):** see block-correction #4 above and Notes for the implementer §7.
- **DP-2 (registry pattern, already realized):** `parsers/_io.open_capped` is the kernel; `_yarn.py` is the third caller. Validated; no action other than AC-3 calling it with `parser_kind="yarn_lockfile"`.
- **DP-3 (strategy pattern, light form):** the `_HAS_PYARN` boolean + an `if/else` inside `parse()` is the simplest possible expression of a two-strategy dispatch. Not refactored to a `_PARSER_FN: Callable[[bytes], YarnLock]` module-level binding because the `pyarn` call sites differ in their I/O shape (path-in vs. bytes-in), and CLAUDE.md Rule 2 again pre-empts the abstraction. Documented in Notes §9.
- **DP-4 (functional core / imperative shell):** `_parse_handrolled(body: bytes) -> YarnLock` is intentionally pure (no I/O). `parse(path)` is the only I/O function. Preserved; the local fuzz script targets `_parse_handrolled` directly, which is testable precisely because of this split. Notes §10.
- **DP-5 (Open/Closed at the family level):** AC-15 pins `_yarn.py` must not reference siblings; AC-1 pins `_lockfiles/__init__.py` non-edit.

No `NEEDS RESEARCH` findings; Stage 3 skipped. The `pyarn` API surface question (DP-7 in the original critic) is implementation work the story already directs the implementer toward (Implementation-outline step 1) and is now pinned by AC-13 — not a researcher question.

## Context

`yarn.lock` is the only Phase 1 lockfile that doesn't have a stdlib-clean parse path: it's neither valid YAML nor JSON. Yarn classic emits a custom indent-sensitive format ("version 1") and Yarn berry emits a YAML-ish format with custom tag conventions. This story ships both code paths and **finalizes ADR-0003 at land-time** by appending an implementer's-selection block to that ADR.

**The decision rule** (ADR-0003):

- `pyarn` last release < 18 months ago (vs. today's date 2026-05-14, so > 2024-11-14) AND fixture suite passes AND no open CVE → ship `pyarn`, list it in `[project.optional-dependencies] gather`.
- Otherwise → ship the hand-rolled line-by-line state-machine scanner (~100 LOC, no regex over full file).

Both code paths return the same `YarnLock` `TypedDict` and produce identical output on the fixture portfolio — that's the load-bearing invariant validated by S3-04's parity + oracle tests.

The hand-rolled scanner is **the single most regex-DoS-prone surface in Phase 1** (`High-level-impl.md §"Implementation-level risks"` #4). Local adversarial fuzzing before the PR is non-negotiable; the dedicated adversarial CI test (`tests/adv/test_regex_dos_yarn_lock.py`) lands in S5-02, not here.

`_yarn.py` is the third concrete consumer of the lockfile-parser shape established in S3-01/S3-02. The rule-of-three threshold is crossed here in principle but the trio is two-of-a-kind (pnpm/npm — both wrap a `safe_X.load` call) plus one-of-a-kind (yarn — wraps `open_capped` directly and dispatches between `pyarn` and a hand-rolled scanner). Validation note block-correction #4 + Notes §7 pin **DEFER** as the resolution. The kernel `parsers/_io.open_capped` is the load-bearing shared abstraction; `_yarn.py` is its third caller, validating the registry-pattern claim from `_io.py`'s docstring.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9 Lockfile parsers` — `_yarn.py` with `_HAS_PYARN: bool` module-level guard; line-by-line state machine (no regex over full file); ~80 ms p50 (`pyarn`) vs. ~200 ms p50 (hand-rolled).
  - `../phase-arch-design.md §"Edge cases"` row 10 — `pyarn` uninstall path during gather → `ImportError` falls back to hand-rolled. Same correctness, ~50 ms slower.
  - `../phase-arch-design.md §"Gap analysis" Gap 3` — two-direction parity (this story **enables**; S3-04 implements the tests).
- **Phase ADRs:**
  - `../ADRs/0003-yarn-lock-parser-choice.md` — **THE ADR THIS STORY FINALIZES.** Read all of it; the "Implementer's land-time selection" block (line 69-71) is empty and **must be filled in this PR**.
  - `../ADRs/0007-warnings-id-pattern.md` — `WarningId` is constructed at the catch site (in `NodeManifestProbe`) from the marker's `args[0]`, not embedded on the exception.
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — caps live in the parser kernel (`open_capped`), not in a per-probe sandbox.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — `pyarn` is the only Phase 1 dep addition; the conditional adoption rule lives here. `pyarn` is pure-Python, not a C extension.
- **Source design:**
  - `../final-design.md §"Components" #4` — three-way lockfile parsers.
  - `../final-design.md §"Conflict-resolution table"` row 5 — the synthesized choice.
  - `../final-design.md §"Open questions deferred to implementation"` #1 — the land-time decision rule.
  - `../critique.md §"Attacks on the performance-first design"` #4 — the 16-ms-average-latency demolition that ruled out hand-rolled-by-default.
  - `../High-level-impl.md §"Step 3"` + `§"Implementation-level risks"` #3, #4.
- **Existing code (Phase 0 + Step 1 + S3-01 + S3-02):**
  - `src/codegenie/parsers/_io.py` — `open_capped(path, *, max_bytes, parser_kind)` from S1-02/S1-03. Returns `bytes`; raises `SizeCapExceeded`, `SymlinkRefusedError`; propagates `FileNotFoundError`, `IsADirectoryError`, `PermissionError`, etc., unchanged. **This is the kernel `_yarn.py` calls.**
  - `src/codegenie/errors.py` — `MalformedLockfileError` is a marker subclass with no `__init__` (Phase 0 invariant). `SizeCapExceeded`, `SymlinkRefusedError` already exist.
  - `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` — parametrizes every Phase 1 marker (incl. `MalformedLockfileError`) for positional construction; asserts `not hasattr(exc, "path" | "cap" | "detail" | "warning_id")`.
  - `src/codegenie/probes/_lockfiles/_pnpm.py` — S3-01 baseline. Mirror its docstring shape (sources block, marker invariant note); substitute the open path and dispatch logic.
  - `src/codegenie/probes/_lockfiles/_npm.py` — S3-02 baseline. Same.
  - `src/codegenie/probes/_lockfiles/__init__.py` — S3-01 settled it as `__all__: list[str] = []`. **S3-03 must NOT edit this file.**
  - `src/codegenie/logging.py` — `EVENT_PROBE_PARSER_CAP_EXCEEDED` is the structured-event name `open_capped` emits with `parser_kind=<literal>`. Test asserts `parser_kind="yarn_lockfile"` surfaces.
  - `pyproject.toml` — Phase 0 ADR-0006 extras shape; the `[project.optional-dependencies] gather` list is the one place `pyarn` may land.
- **External docs:**
  - PyPI page for `pyarn` (https://pypi.org/project/pyarn/) — **read at PR-open time** to pin last-release date in the ADR.
  - `pyarn` GitHub repo issue tracker — scan for open CVEs / unmaintained-fork warnings.
- **Validation precedents (the marker + family discipline already settled):**
  - `_validation/S1-02-safe-json-parser.md`, `_validation/S1-03-safe-yaml-parser.md` — first kwargs-on-markers correction; established `f"{path}: {type(cause).__name__}: {cause}"` format.
  - `_validation/S3-01-pnpm-lockfile-parser.md` — established the lockfile-parser shape S3-03 mirrors; pinned `_lockfiles/__init__.py` as inert.
  - `_validation/S3-02-npm-lockfile-parser.md` — reinforced the inert-`__init__` invariant; deferred `_translate` extraction to S3-03 land-time.

## Goal

Implement `src/codegenie/probes/_lockfiles/_yarn.py` with `_HAS_PYARN: bool` module-level dispatch, ship the hand-rolled scanner unconditionally, call the shared `parsers/_io.open_capped` kernel for the pre-parse defenses, translate parse failures to `MalformedLockfileError` (positional message, `__cause__` preserved), and append the implementer's land-time selection note to `ADR-0003` — so `NodeManifestProbe` can call `_yarn.parse(path)` and get a `YarnLock` `TypedDict` regardless of `pyarn` install state. S3-03 adds **one new file** to `src/` (`_yarn.py`), **does not edit** `_lockfiles/__init__.py` (CLAUDE.md "Extension by addition" — inherits the inert form from S3-01/S3-02), and conditionally edits `pyproject.toml` plus mandatorily edits `ADR-0003`.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/_lockfiles/__init__.py` is **not edited** by S3-03. The file content as committed by S3-01 (and re-asserted by S3-02) remains byte-for-byte unchanged. Pinned by the same architectural test S3-02 introduced (`test_lockfiles_init_remains_inert`); test is re-run on S3-03's branch.
- [ ] **AC-2.** `src/codegenie/probes/_lockfiles/_yarn.py` exports exactly `__all__ = ["YarnLock", "YarnLockEntry", "parse"]`.
- [ ] **AC-3.** `parse(path: Path) -> YarnLock` calls `open_capped(path, max_bytes=YARN_LOCKFILE_MAX_BYTES, parser_kind="yarn_lockfile")` from `codegenie.parsers._io` to perform the pre-parse `O_NOFOLLOW` open + `os.fstat` size check. **No in-module reimplementation** of either defense (the kernel is the single source of truth per `_io.py`'s docstring). Module constants `YARN_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024` and `_PARSER_KIND: Final[str] = "yarn_lockfile"` declared at module scope.
- [ ] **AC-4.** `_HAS_PYARN: bool = importlib.util.find_spec("pyarn") is not None` computed at module load. The `find_spec` call is the **only** runtime probe for `pyarn` availability — no `try: import pyarn` at module top-level (that would import the module even when we want the hand-rolled path).
- [ ] **AC-5.** `parse(path)` dispatches on `_HAS_PYARN`: if `True`, defers to the `pyarn` path; if `False`, calls `_parse_handrolled(body)`. Both branches receive the **same** `body: bytes` from `open_capped` — `pyarn` is never invoked with a raw `Path` (so the size-cap defense holds regardless of `pyarn`'s internal file-handling behavior).
- [ ] **AC-6.** `parse(path)` **re-raises unchanged** any `SizeCapExceeded` or `SymlinkRefusedError` raised by `open_capped`. No re-wrapping, no swallowing. (`open_capped` does not raise `DepthCapExceeded` — yarn.lock has no nested-document depth concept; depth-cap is irrelevant to this parser.)
- [ ] **AC-7.** On any other parse failure raised by either dispatch path (`pyarn`'s exceptions; the hand-rolled scanner's `ValueError` / `UnicodeDecodeError` / `IndexError`), `parse(path)` translates to `MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}")` raised `from cause`. Per ADR-0003 §"Reversibility" + Notes §11: the hand-rolled scanner does **not** fall back to `pyarn` on parse error, nor vice-versa — the parity test in S3-04 owns the bidirectional correctness contract, and a silent fallback would muddy it.
- [ ] **AC-8.** **Marker contract preserved.** The raised `MalformedLockfileError` carries its message in `args[0]` only; `hasattr(exc, "path")`, `hasattr(exc, "cause")`, etc. are all **False**. The Phase 0 invariant `tests/unit/test_errors.py::test_subclasses_are_markers_only` is unaffected by S3-03 code.
- [ ] **AC-9.** **`__cause__` chain.** For the malformed-bytes path, `exc.__cause__ is not None` and `type(exc.__cause__).__name__` appears in `exc.args[0]` (so observability can trace which underlying parser surfaced the error without needing typed attributes).
- [ ] **AC-10.** **Path observability via message, not attribute.** The raised `MalformedLockfileError`'s `args[0]` contains `str(path)` as a substring (so downstream `WarningId` construction in `NodeManifestProbe` can recover the path from `args[0]` without instance state).
- [ ] **AC-11.** **`YarnLock(TypedDict, total=False)`** declares at minimum `entries: dict[str, YarnLockEntry]`. **`YarnLockEntry(TypedDict, total=False)`** declares at minimum `version: str`, `resolved: str`, `integrity: str`, `dependencies: dict[str, str]`. The `total=False` flag is **load-bearing** — yarn classic v1 may omit `integrity`; yarn berry may include fields outside this minimum. Defaulting at the parser layer is forbidden (consumer-side concern; `NodeManifestProbe` reconciles in S3-05).
- [ ] **AC-12.** **No regex over the full file.** The hand-rolled scanner is a line-by-line state machine (entry header → key/value pairs → next header). `re.compile(...).search/match/findall` on `body` as a whole is rejected at review. Per-line bounded regex (e.g., `re.match(r'^([^"]+) "([^"]*)"$', stripped_line)`) is allowed but discouraged in favor of `str.startswith` / `str.partition`. Pinned by an architectural test that asserts the module text contains no occurrence of `re.compile` or `re.search`/`re.findall`/`re.match` at module scope (line-bounded regex inside the parser loop is permitted; the test scans for forbidden patterns conservatively).
- [ ] **AC-13.** **`pyarn` API surface verified at land-time.** The implementer must confirm `pyarn`'s public API on the version selected (PyPI page + repo `__init__.py`) and adjust the dispatch call in `_pyarn_parse` accordingly. The Green code below sketches `pyarn.lockfile.Lockfile.from_file(path)` and `pyarn.lockfile.Lockfile.from_string(body.decode("utf-8"))` as the most-likely shapes; the implementer either confirms one of these or amends ADR-0003's land-time-selection block to record the actual API used. **If the API doesn't fit the dispatch contract (body-bytes-in, `YarnLock`-out), the land-time decision flips to hand-rolled** — Rule 12 (fail loud): an API mismatch is a decision, not a deferral.
- [ ] **AC-14.** **`pyproject.toml`** lists `pyarn` under `[project.optional-dependencies] gather` **iff the land-time decision selects `pyarn`**. If the decision is hand-rolled, `pyarn` is **not** in the dependency closure. (`pyarn`'s minimum version is pinned per ADR-0003's land-time block.)
- [ ] **AC-15.** **ADR-0003's "Implementer's land-time selection" block** at lines 69-71 of `docs/phases/01-context-gather-layer-a-node/ADRs/0003-yarn-lock-parser-choice.md` is **filled in this PR** with: today's date (`2026-05-14` or later), the selection (`pyarn` or `hand-rolled`), pinned `pyarn` last-release date (from PyPI), the CVE-scan result (from OSV / GHSA), the fixture-suite pass/fail confirmation, the verified `pyarn` API surface (per AC-13), and the rationale sentence. Pinned by a checklist line in PR-template + a documentation-only test that grep's the ADR text for the "Implementer's land-time selection (YYYY-MM-DD)" header pattern.
- [ ] **AC-16.** **Local fuzz of the hand-rolled scanner** completed before opening the PR via `tools/fuzz_yarn_lock.py` (committed throwaway script; not in `tests/`, not pytest-collected). The script byte-mutates a real `tests/fixtures/node_yarn_legacy/yarn.lock` ≥ 1000 times under a 1-second per-iteration `signal.alarm` timeout; the worst-case wall-clock is pasted into the PR body. The corpus for adversarial CI is S5-02's job; this AC is the implementer-side first-defense per `High-level-impl.md §"Implementation-level risks"` #4.
- [ ] **AC-17.** **Extension-by-addition.** Adding a future sibling parser (e.g., `_bun.py` for `bun.lockb`) requires **zero edits** to `_yarn.py`. Pinned via an architectural test that asserts `_yarn.py`'s module text contains no string occurrences of `"_pnpm"`, `"_npm"`, or `"_bun"` (sibling parsers don't import each other; the shared kernels are `parsers/_io.open_capped` + `codegenie.errors`).
- [ ] **AC-18.** **`parser_kind` observability.** The structured event `probe.parser.cap_exceeded` emitted by `open_capped` when the size cap fires carries `parser_kind="yarn_lockfile"` — pinned by a `structlog`-capture test (asserts the event surfaces with the literal discriminator the registry pattern demands).
- [ ] **AC-19.** **Module hygiene.** `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/probes/_lockfiles/_yarn.py`, and the unit-test module pass. The cast `cast(YarnLock, ...)` is the **only** runtime-no-op present; no schema validation, no field defaulting, no key reshaping. `fence` CI job continues green — `pyarn` is **not** an LLM SDK and `fence` confirms.
- [ ] **AC-20.** **TDD discipline.** The red marker commit lands first (`ModuleNotFoundError: codegenie.probes._lockfiles._yarn`); each failure-path test asserts the **specific** typed exception class (not just `CodegenieError`); the happy-path tests assert dict-shape, not value-equality of nested structures (that's `NodeManifestProbe`'s concern); the malformed-bytes test forces the hand-rolled path via `monkeypatch.setattr(_yarn, "_HAS_PYARN", False)` so the assertion is deterministic regardless of `pyarn`'s local install state.
- [ ] **AC-21.** **Marker-attribute negative.** A parametrized test asserts that for every typed exception this module *can* raise (`SizeCapExceeded`, `SymlinkRefusedError`, `MalformedLockfileError`), the caught instance has `args == (some_str,)` and `not hasattr(exc, "path" | "cap" | "detail" | "cause" | "warning_id")` — pins the marker discipline against silent regressions.

## Implementation outline

1. **First — evaluate `pyarn`'s status.** Open the PyPI page (https://pypi.org/project/pyarn/) and the GitHub repo. Pin the last-release date. Scan open issues / GitHub Security Advisories for `pyarn` (OSV + GHSA feeds). Run the heuristic in ADR-0003:
   - Last release > 2024-11-14 (i.e., < 18 months ago vs. 2026-05-14)?
   - No open CVE in the OSV / GHSA feed?
   - Does `pyarn` parse the Phase 1 fixture `tests/fixtures/node_yarn_legacy/yarn.lock` (S3-06) without error? (You may need to pre-land the fixture as part of this PR or land alongside S3-06; note which path you took in the ADR block.)
   - **Verify `pyarn`'s actual API** (AC-13): inspect `pyarn.__init__.py` for the public surface. Modern `pyarn` exposes `Lockfile.from_file(path)` or `Lockfile.from_string(body)`; the dispatch wrapper `_pyarn_parse(body: bytes, *, path: Path) -> YarnLock` must adapt to the actual shape.
2. **Use the shared kernel for the open + size-check.** Call `open_capped(path, max_bytes=YARN_LOCKFILE_MAX_BYTES, parser_kind="yarn_lockfile")` from `codegenie.parsers._io`. **Do NOT reimplement** `O_NOFOLLOW` / `os.fstat`/ `ELOOP` handling. The kernel exposes a stable `parser_kind: str` discriminator that surfaces on `probe.parser.cap_exceeded` events — `yarn_lockfile` is the literal this module owns.
3. **Implement `_parse_handrolled(body: bytes) -> YarnLock`** — a line-by-line state machine:
   - Iterate `body.decode("utf-8").splitlines()`. (No `errors="replace"`; invalid UTF-8 surfaces as `UnicodeDecodeError` → translated to `MalformedLockfileError` per AC-7.)
   - States: `awaiting_entry`, `in_entry_header`, `in_entry_body`.
   - Entry header: starts at column 0, no leading whitespace, ends with `:`.
   - Entry body: lines starting with 2-space indent; parse `key value` or `key "value"`.
   - Sub-blocks (`dependencies:`, `optionalDependencies:`): 4-space indent.
   - **No regex** over the full body; per-line `str.startswith` / `str.split` are fine.
4. **Implement `_pyarn_parse(body: bytes, *, path: Path) -> YarnLock`** — a thin adapter around `pyarn`'s actual API (verified per AC-13). On any `pyarn` exception, let it propagate; `parse()` translates uniformly.
5. **Implement `parse(path)`**:
   - `body = open_capped(path, max_bytes=YARN_LOCKFILE_MAX_BYTES, parser_kind="yarn_lockfile")` — `SizeCapExceeded` / `SymlinkRefusedError` propagate unchanged.
   - Dispatch on `_HAS_PYARN`. Wrap the dispatch call in `try: ... except (SizeCapExceeded, SymlinkRefusedError): raise; except Exception as cause: raise MalformedLockfileError(f"{path}: {type(cause).__name__}: {cause}") from cause`.
   - **Do NOT fall back** between dispatch paths on parse error — Notes §11 + AC-7.
6. **Update `pyproject.toml`** conditionally — add `pyarn` to `[project.optional-dependencies] gather` only if the land-time decision selects `pyarn`. Otherwise the file is unchanged.
7. **Local fuzz before PR** (AC-16): write `tools/fuzz_yarn_lock.py`; commit it. Run it; capture the output line and paste into PR body. Script targets `_parse_handrolled` directly (functional-core / imperative-shell pays off here).
8. **Append the land-time selection to `ADR-0003`** (AC-15) per the documented "Implementer's land-time selection (YYYY-MM-DD)" header pattern from ADR-0003 §Consequences final bullet.

**Explicitly NOT touched:** `src/codegenie/probes/_lockfiles/__init__.py` (AC-1).

**No constructor extension of `MalformedLockfileError`.** The marker contract is frozen per Phase 0 invariant + S1-01 parametrized tests. Path lives in `args[0]`; cause lives on `__cause__` via `raise ... from cause`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/_lockfiles/test_yarn.py`. Each test is annotated with its AC and the mutation it catches.

```python
# tests/unit/probes/_lockfiles/test_yarn.py
"""Unit tests for ``codegenie.probes._lockfiles._yarn``.

Each test is keyed to an AC in S3-03 and names the mutation it catches in
its docstring (mutation-resistance per Rule 9 — tests verify intent).
"""
from __future__ import annotations

import importlib.util
import inspect
import os
from pathlib import Path
from typing import Any

import pytest

from codegenie.errors import (
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.probes._lockfiles import _yarn


YARN_LOCK_MINIMAL = """\
# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.
# yarn lockfile v1


bcrypt@^5.1.0:
  version "5.1.1"
  resolved "https://registry.yarnpkg.com/bcrypt/-/bcrypt-5.1.1.tgz"
  integrity sha512-AGBHOG5...
  dependencies:
    node-addon-api "^5.0.0"
"""


# --- AC-2, AC-11, AC-20 — happy path on the hand-rolled path -------------------


def test_parse_happy_path_handrolled_yields_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-11, AC-20. Force the hand-rolled path so the assertion is
    deterministic regardless of pyarn install state.

    Mutation caught: state-machine never enters in_entry_body (entries
    dict stays empty); ValueError("no yarn.lock entries parsed") raised
    instead of returning shaped dict. Asserts entry header keys and the
    minimum version-field shape.
    """
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text(YARN_LOCK_MINIMAL)
    result = _yarn.parse(lockfile)
    assert "bcrypt@^5.1.0" in result["entries"]
    assert result["entries"]["bcrypt@^5.1.0"]["version"] == "5.1.1"


def test_parse_handrolled_total_false_admits_missing_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-11. Mutation caught: ``total=True`` on YarnLockEntry would
    require ``integrity`` on every entry; yarn classic ≤ v1.21 omitted
    integrity hashes — the parser must not default them. The runtime
    assertion is the lookup; the load-bearing check is mypy --strict."""
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    body = (
        "# yarn lockfile v1\n\n"
        "lodash@^4.17.0:\n"
        '  version "4.17.21"\n'
        '  resolved "https://example.invalid/lodash-4.17.21.tgz"\n'
    )
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text(body)
    result = _yarn.parse(lockfile)
    assert "integrity" not in result["entries"]["lodash@^4.17.0"]
    assert result["entries"]["lodash@^4.17.0"]["version"] == "4.17.21"


# --- AC-6 — size cap (re-raised unchanged from open_capped) --------------------


def test_parse_oversized_file_reraises_size_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-6. Mutation caught: swallowing SizeCapExceeded into
    MalformedLockfileError (broad ``except Exception`` instead of the
    explicit passthrough). Uses ``os.fstat`` monkey-patch instead of
    writing 60 MB to tmpfs (Rule 2)."""
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text(YARN_LOCK_MINIMAL)

    real_fstat = os.fstat

    class FakeStat:
        def __init__(self, st: os.stat_result) -> None:
            self._st = st

        st_size = 60 * 1024 * 1024
        st_mode = property(lambda self: self._st.st_mode)  # type: ignore[no-redef]

    def fake_fstat(fd: int) -> Any:  # noqa: ANN401 — stub mirrors stdlib
        return FakeStat(real_fstat(fd))

    monkeypatch.setattr(os, "fstat", fake_fstat)
    with pytest.raises(SizeCapExceeded):
        _yarn.parse(lockfile)


# --- AC-6 — symlink refusal (re-raised unchanged from open_capped) -------------


def test_parse_symlink_at_final_component_reraises_symlink_refused(
    tmp_path: Path,
) -> None:
    """AC-6. Mutation caught: any path that catches SymlinkRefusedError
    in the dispatch try/except and re-wraps it as MalformedLockfileError.
    The wrapper inherits open_capped's defense and must let the
    exception propagate unchanged."""
    real = tmp_path / "real.lock"
    real.write_text(YARN_LOCK_MINIMAL)
    link = tmp_path / "yarn.lock"
    link.symlink_to(real)
    with pytest.raises(SymlinkRefusedError):
        _yarn.parse(link)


# --- AC-7, AC-9, AC-10, AC-20 — malformed-bytes translation --------------------


def test_parse_malformed_bytes_handrolled_translates_to_malformed_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-7, AC-9. Mutation caught: dropping ``from cause`` (loses
    ``__cause__``); catching ``BaseException`` (would absorb KeyboardInterrupt);
    translating to a different marker class. Hand-rolled path is
    deterministic — pyarn's parse-error behavior is its own contract,
    not ours."""
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text("malformed garbage with no entry header structure\n@@@@@\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _yarn.parse(lockfile)
    # AC-9: __cause__ is some real exception (ValueError from the scanner).
    assert exc.value.__cause__ is not None
    # The cause's type name surfaces in the message for observability.
    assert type(exc.value.__cause__).__name__ in exc.value.args[0]


def test_parse_malformed_bytes_message_contains_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-10. Mutation caught: building the message without the path
    (e.g., ``MalformedLockfileError(str(cause))``) — downstream WarningId
    construction in NodeManifestProbe recovers the path from
    ``args[0]``."""
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text("not a yarn lockfile at all\n@@@\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _yarn.parse(lockfile)
    assert str(lockfile) in exc.value.args[0]


def test_parse_invalid_utf8_handrolled_translates_to_malformed_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-7. Mutation caught: ``body.decode("utf-8", errors="replace")``
    would silently substitute the lossy character (U+FFFD) and the
    parser would attempt to scan garbage — surfacing a confusing
    ValueError far from the real cause. Using strict decode means
    UnicodeDecodeError surfaces directly and is translated cleanly."""
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_bytes(b"# yarn lockfile v1\n\n\xff\xfe\xfd: invalid utf8 header\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _yarn.parse(lockfile)
    assert isinstance(exc.value.__cause__, (UnicodeDecodeError, ValueError))


# --- AC-4 — _HAS_PYARN semantics ----------------------------------------------


def test_has_pyarn_reflects_find_spec_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-4. Mutation caught: probing pyarn via ``try: import pyarn``
    would (a) import the module unconditionally, defeating the no-import
    branch, and (b) catch errors other than ImportError. The probe must
    be ``importlib.util.find_spec``."""
    # Import the module fresh to re-evaluate _HAS_PYARN.
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "pyarn":
            return object()  # truthy non-None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    import importlib as _importlib

    reloaded = _importlib.reload(_yarn)
    try:
        assert reloaded._HAS_PYARN is True
    finally:
        _importlib.reload(_yarn)  # restore module state for siblings


def test_has_pyarn_reflects_find_spec_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-4. Mutation caught: a hard-coded ``_HAS_PYARN = True`` (or
    False) would pass every other test depending on local install
    state. find_spec returning None must drive the flag."""
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "pyarn":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    import importlib as _importlib

    reloaded = _importlib.reload(_yarn)
    try:
        assert reloaded._HAS_PYARN is False
    finally:
        _importlib.reload(_yarn)


# --- AC-8, AC-21 — marker discipline ------------------------------------------


def test_raised_marker_has_no_instance_attributes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-8, AC-21. Mutation caught: a future "convenience" override of
    ``MalformedLockfileError.__init__(self, *, path, cause)`` would be
    flagged immediately. The Phase-0 invariant
    ``test_subclasses_are_markers_only`` already guards the class-level
    contract; this test guards the construction site in _yarn.py."""
    monkeypatch.setattr(_yarn, "_HAS_PYARN", False)
    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text("@@@@@ not a yarn lock\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _yarn.parse(lockfile)
    # Marker invariant: args is a single positional message string.
    assert len(exc.value.args) == 1
    assert isinstance(exc.value.args[0], str)
    # Negatives — no instance attributes smuggled in.
    for forbidden in ("path", "cap", "detail", "cause", "warning_id"):
        assert not hasattr(exc.value, forbidden), (
            f"MalformedLockfileError must remain a marker; instance must not "
            f"carry {forbidden!r}. Path lives in args[0]; cause lives on __cause__."
        )


# --- AC-12 — no regex over full file -----------------------------------------


def test_yarn_module_does_not_run_regex_over_full_file() -> None:
    """AC-12. Mutation caught: a future "optimization" that replaces the
    line-by-line state machine with ``re.compile(...).findall(body)`` —
    that is the regex-DoS-prone shape this module is explicitly
    forbidden from adopting. Per-line bounded regex inside the loop is
    allowed (the test scans for module-scope ``re.compile`` and
    full-body ``re.search``/``re.findall``/``re.match`` patterns).

    This is conservative — false positives are acceptable; false
    negatives (a real DoS-prone pattern slipping through) are not.
    """
    src = inspect.getsource(_yarn)
    # Module-scope ``re.compile`` would suggest a pre-compiled full-file
    # regex; we forbid the import entirely as the simplest pin.
    assert "import re" not in src, (
        "_yarn.py must not import ``re``; the hand-rolled scanner is a "
        "state machine, not a regex. Adversarial regex-DoS lands in S5-02."
    )


# --- AC-17 — extension-by-addition (architectural test) ----------------------


def test_yarn_module_does_not_reference_sibling_parsers() -> None:
    """AC-17, CLAUDE.md "Extension by addition". Mutation caught: a
    future edit that imports ``_pnpm`` / ``_npm`` / ``_bun`` into
    ``_yarn`` — sibling parsers must be free to evolve independently.
    The shared kernels are ``parsers/_io.open_capped`` +
    ``codegenie.errors``, not other sibling modules."""
    src = inspect.getsource(_yarn)
    for forbidden in ("_pnpm", "_npm", "_bun"):
        assert forbidden not in src, (
            f"_yarn.py must not reference sibling parser {forbidden!r}; "
            f"adding a new lockfile format is a new file, not an edit here."
        )


# --- AC-1 — _lockfiles/__init__.py stays inert (S3-03 doesn't edit it) ------


def test_lockfiles_init_remains_inert() -> None:
    """AC-1, CLAUDE.md "Extension by addition". S3-01 settled the
    family-__init__ as inert; S3-02 reinforced; S3-03 must not touch
    it. The contract: ``__all__: list[str] = []`` and sibling parsers
    export from their own modules."""
    from codegenie.probes import _lockfiles

    assert getattr(_lockfiles, "__all__", None) == [], (
        "_lockfiles/__init__.py is settled as inert by S3-01 — S3-03 must "
        "not re-export YarnLock through it. Consumers import siblings directly."
    )
    for forbidden in ("PnpmLock", "NpmLock", "YarnLock", "YarnLockEntry"):
        assert not hasattr(_lockfiles, forbidden), (
            f"{forbidden} must be imported from its sibling module, not "
            f"the package __init__. Phase 2 may revisit if extracting a "
            f"shared helper into the package (rule of three)."
        )


# --- AC-18 — parser_kind discriminator surfaces on cap-exceeded event ---------


def test_parser_kind_yarn_lockfile_surfaces_on_size_cap_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-18. Mutation caught: passing ``parser_kind="safe_yaml"`` or
    omitting it would defeat the registry-pattern's payoff — downstream
    observability can no longer attribute the cap violation to the
    yarn-lockfile parser specifically. Test asserts the literal surfaces
    on the structured event."""
    import structlog
    from codegenie.logging import EVENT_PROBE_PARSER_CAP_EXCEEDED

    events: list[dict[str, Any]] = []

    def capture(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        events.append(dict(event_dict))
        return event_dict

    structlog.configure(processors=[capture])

    lockfile = tmp_path / "yarn.lock"
    lockfile.write_text(YARN_LOCK_MINIMAL)

    real_fstat = os.fstat

    class FakeStat:
        def __init__(self, st: os.stat_result) -> None:
            self._st = st

        st_size = 60 * 1024 * 1024
        st_mode = property(lambda self: self._st.st_mode)  # type: ignore[no-redef]

    def fake_fstat(fd: int) -> Any:  # noqa: ANN401
        return FakeStat(real_fstat(fd))

    monkeypatch.setattr(os, "fstat", fake_fstat)
    with pytest.raises(SizeCapExceeded):
        _yarn.parse(lockfile)
    cap_events = [e for e in events if e.get("event") == EVENT_PROBE_PARSER_CAP_EXCEEDED]
    assert any(e.get("parser_kind") == "yarn_lockfile" for e in cap_events), (
        f"Expected parser_kind='yarn_lockfile' on a {EVENT_PROBE_PARSER_CAP_EXCEEDED!r} "
        f"event; got {cap_events!r}"
    )
```

Run `pytest tests/unit/probes/_lockfiles/test_yarn.py` — fails with `ModuleNotFoundError: codegenie.probes._lockfiles._yarn`. Commit the red marker.

### Green — make it pass

```python
# src/codegenie/probes/_lockfiles/_yarn.py
"""yarn.lock parser — pyarn if available at runtime, else hand-rolled scanner.

Yarn classic emits a custom indent-sensitive format ("version 1") that is
neither JSON nor YAML; yarn berry emits a YAML-ish format with custom
tag conventions. This module ships **both** code paths and dispatches at
module load via ``_HAS_PYARN: bool`` (computed via
``importlib.util.find_spec``). The ADR-0003 land-time selection
determines whether ``pyarn`` is listed in ``pyproject.toml``'s ``gather``
extras; either way the hand-rolled scanner ships unconditionally so
contributors without ``pyarn`` installed still parse correctly (arch
§"Edge cases" row 10).

Both dispatch paths receive the same ``body: bytes`` from
:func:`codegenie.parsers._io.open_capped` — ``pyarn`` is never invoked
with a raw ``Path``, so the size-cap + ``O_NOFOLLOW`` defenses hold
regardless of ``pyarn``'s internal file-handling behavior.

Parse failures from either path are translated to
:class:`MalformedLockfileError` (positional message, ``__cause__``
preserved). ``SizeCapExceeded`` and ``SymlinkRefusedError`` from
``open_capped`` propagate unchanged. There is **no fall-back** between
dispatch paths on parse error — the parity test in S3-04 owns the
bidirectional correctness contract, and a silent fall-back would muddy
it (arch §"Edge cases" row 10 covers the *uninstall* fall-back via
``_HAS_PYARN``; it does not cover *parse-error* fall-back).

The hand-rolled scanner is a **line-by-line state machine** — there is
no regex over the full file. Adversarial regex-DoS testing lands in
S5-02 (`tests/adv/test_regex_dos_yarn_lock.py`). Local fuzz before PR
is non-negotiable (S3-03 AC-16; arch's High-level-impl.md §"Step 3"
risk #4).

Sources:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #9 — interface and ~80 ms (pyarn) / ~200 ms
  (hand-rolled) p50 budget.
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0003-yarn-lock-parser-choice.md`` (the land-time decision rule),
  ``0007-warnings-id-pattern.md`` (WarningId at catch site),
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (caps via
  open_capped), ``0009-no-new-c-extension-parser-dependencies.md``
  (pyarn is the one conditional Phase 1 dep).

Phase-0 marker invariant: :class:`MalformedLockfileError` accepts a
single positional message string; the path lives in ``args[0]``, the
cause lives on ``__cause__`` via ``raise ... from cause``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Final, TypedDict, cast

from codegenie.errors import (
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.parsers._io import open_capped

__all__ = ["YarnLock", "YarnLockEntry", "parse"]

YARN_LOCKFILE_MAX_BYTES: Final[int] = 50 * 1024 * 1024
_PARSER_KIND: Final[str] = "yarn_lockfile"

_HAS_PYARN: bool = importlib.util.find_spec("pyarn") is not None


class YarnLockEntry(TypedDict, total=False):
    """One entry from a parsed ``yarn.lock``. ``total=False`` is load-bearing.

    Yarn classic ≤ v1.21 omitted ``integrity``; berry may include fields
    outside this minimum. ``NodeManifestProbe`` (S3-05) reconciles.
    """

    version: str
    resolved: str
    integrity: str
    dependencies: dict[str, str]


class YarnLock(TypedDict, total=False):
    """Parsed ``yarn.lock`` shape — ``total=False`` is load-bearing.

    The ``entries`` keys are raw yarn-lock identifiers (e.g.
    ``"bcrypt@^5.1.0"``), possibly comma-joined for shared resolutions
    like ``"foo@^1.0, foo@^1.1"``. ``NodeManifestProbe`` (S3-05) splits
    on ``, `` when reconciling.
    """

    entries: dict[str, YarnLockEntry]


def _parse_handrolled(body: bytes) -> YarnLock:
    """Line-by-line state machine; no regex over the full body.

    Raises:
        UnicodeDecodeError: ``body`` is not valid UTF-8 (translated by
            :func:`parse`).
        ValueError: structural error in the lockfile (translated by
            :func:`parse`).
    """
    entries: dict[str, YarnLockEntry] = {}
    current_key: str | None = None
    current_entry: dict[str, Any] = {}
    current_subblock: str | None = None  # "dependencies" / "optionalDependencies" / None

    # Strict UTF-8 decode — invalid bytes surface as UnicodeDecodeError,
    # which parse() translates to MalformedLockfileError per AC-7. This
    # is the deliberate fail-loud (Rule 12) choice: ``errors="replace"``
    # would substitute U+FFFD and the scanner would chase garbage.
    text = body.decode("utf-8")

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            if current_key is not None:
                entries[current_key] = cast(YarnLockEntry, current_entry)
            if not line.endswith(":"):
                raise ValueError(
                    f"expected entry header ending in ':', got {line!r}"
                )
            current_key = line[:-1].strip().strip('"')
            current_entry = {}
            current_subblock = None
        elif line.startswith("    ") and current_subblock is not None:
            k, _, v = line.strip().partition(" ")
            current_entry.setdefault(current_subblock, {})[k.strip('"')] = v.strip('"')
        elif line.startswith("  "):
            stripped = line.strip()
            if stripped in ("dependencies:", "optionalDependencies:"):
                current_subblock = stripped[:-1]
                continue
            current_subblock = None
            k, _, v = stripped.partition(" ")
            current_entry[k.strip('"')] = v.strip('"')

    if current_key is not None:
        entries[current_key] = cast(YarnLockEntry, current_entry)
    if not entries:
        raise ValueError("no yarn.lock entries parsed")
    return {"entries": entries}


def _pyarn_parse(body: bytes) -> YarnLock:
    """Adapter around the installed ``pyarn`` package.

    The exact API surface is verified at land-time per S3-03 AC-13 and
    pinned in ADR-0003's "Implementer's land-time selection" block.
    Most-likely shapes (modern pyarn):

    - ``pyarn.lockfile.Lockfile.from_string(body.decode("utf-8")).data``
    - ``pyarn.lockfile.Lockfile.from_string(body.decode("utf-8")).to_dict()``

    Implementer: replace the body of this function with the verified
    call. Any exception from pyarn propagates and is translated to
    :class:`MalformedLockfileError` by :func:`parse`.
    """
    # Placeholder shape — replace with the verified pyarn call per AC-13.
    # The structure below is illustrative; the land-time selection block
    # in ADR-0003 must record the exact API call used here.
    import pyarn.lockfile  # type: ignore[import-not-found]

    lock = pyarn.lockfile.Lockfile.from_string(body.decode("utf-8"))
    raw: dict[str, Any] = (
        lock.to_dict() if hasattr(lock, "to_dict") else dict(getattr(lock, "data", {}))
    )
    return cast(YarnLock, {"entries": cast(dict[str, YarnLockEntry], raw)})


def parse(path: Path) -> YarnLock:
    """Parse a ``yarn.lock`` under the 50 MB cap via the shared kernel.

    Raises:
        SizeCapExceeded: re-raised unchanged from ``open_capped``.
        SymlinkRefusedError: re-raised unchanged from ``open_capped``.
        MalformedLockfileError: translated from any other parse-time
            exception (``UnicodeDecodeError``, ``ValueError`` from the
            hand-rolled scanner; ``pyarn``'s own exception classes on
            the pyarn path). The original is preserved on
            ``__cause__``. The message in ``args[0]`` includes
            ``str(path)`` so downstream ``WarningId`` construction can
            recover it.
        FileNotFoundError: propagated from the underlying open.
    """
    body = open_capped(path, max_bytes=YARN_LOCKFILE_MAX_BYTES, parser_kind=_PARSER_KIND)
    try:
        if _HAS_PYARN:
            return _pyarn_parse(body)
        return _parse_handrolled(body)
    except (SizeCapExceeded, SymlinkRefusedError):
        raise
    except Exception as cause:
        raise MalformedLockfileError(
            f"{path}: {type(cause).__name__}: {cause}"
        ) from cause
```

### Refactor

- **Module constants stay per-file.** They are identical across pnpm/npm/yarn (50 MB cap); lifting them to `_lockfiles/__init__.py` would create a backward-edge that retrofits S3-01/S3-02. **Decision: deferred (DP-1 in Validation notes; rule of three says "extract on the third concrete consumer" but yarn's shape diverges enough that the trio is two-of-a-kind plus one-of-a-kind).** Phase 2 can revisit if a fourth lockfile reveals the right shape.
- **The `try/except Exception as cause` block is broader than `_pnpm.py`'s / `_npm.py`'s narrow `MalformedYAMLError` / `MalformedJSONError` catches.** This is deliberate: yarn dispatches across two parsers (pyarn, hand-rolled), each with its own exception zoo. A narrow catch on this path would silently swallow novel exception types from `pyarn` upgrades. The explicit passthrough of `(SizeCapExceeded, SymlinkRefusedError)` keeps the marker contract intact.
- **`_pyarn_parse` is intentionally placeholder-shaped.** The implementer fills it in per the verified `pyarn` API surface at land-time (AC-13) and records the verified shape in ADR-0003's land-time-selection block. If `pyarn`'s API doesn't fit the contract (body-bytes-in, `YarnLock`-out), the land-time decision flips to hand-rolled (Rule 12; AC-13's last sentence).
- **The cast to `YarnLock`** in both dispatch paths is a runtime no-op. If a future change adds a structural validator, it lives in `NodeManifestProbe`, not here.
- **Hand-rolled scanner key-comma-splitting.** A yarn-lock entry header `"foo@^1.0, foo@^1.1":` is stored as a single dict key — the comma split is `NodeManifestProbe`'s job per Notes §12.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/_lockfiles/_yarn.py` | New file — `YarnLock` / `YarnLockEntry` TypedDicts + `_HAS_PYARN` + `_parse_handrolled` + `_pyarn_parse` + `parse()` wrapper. |
| `tests/unit/probes/_lockfiles/test_yarn.py` | New file — twelve tests, each keyed to one or more ACs. |
| `tools/fuzz_yarn_lock.py` | New throwaway script — committed but not pytest-collected. Local fuzz harness per AC-16. |
| `pyproject.toml` | Edit (conditional) — add `pyarn` to `[project.optional-dependencies] gather` if land-time decision selects it (AC-14). |
| `docs/phases/01-context-gather-layer-a-node/ADRs/0003-yarn-lock-parser-choice.md` | Edit — fill in the "Implementer's land-time selection (YYYY-MM-DD)" block (AC-15). |

**Explicitly NOT touched:** `src/codegenie/probes/_lockfiles/__init__.py` (AC-1; S3-01's settled inert form; S3-02 reinforced; S3-03 inherits).

## Out of scope

- **Parity + oracle tests** — S3-04. This story ships the parser; S3-04 validates that `pyarn` and hand-rolled agree.
- **Adversarial regex-DoS test in CI** — S5-02 (`test_regex_dos_yarn_lock.py`). Local fuzzing before PR is required (AC-16); the CI-gated adversarial test lives in Step 5.
- **`NodeManifestProbe` integration** — S3-05. This module is a leaf.
- **Yarn Berry (yarn 2/3/4) `.pnp.cjs`** — not in scope; berry repos with `yarn.lock` still parse here, but `.pnp.cjs` is not consumed.
- **Lockfile-version detection** — yarn classic v1 vs. v2+ YAML-style is `pyarn`'s problem in the `_HAS_PYARN=True` path; the hand-rolled scanner targets v1 (the dominant legacy format the fixture portfolio carries).
- **Multi-specifier key splitting** (`"foo@^1.0, foo@^1.1":` → two entries) — `NodeManifestProbe` (S3-05) splits on `, ` when reconciling; parser stores the raw key.
- **Extraction of a shared `_translate(path, *, cause)` helper** — DP-1 deferred per Validation notes block-correction #4. Phase 2 can revisit if a fourth lockfile reveals the right shape.
- **Editing `_lockfiles/__init__.py`** — S3-01 settled it; AC-1 pins the non-edit; S3-02's `test_lockfiles_init_remains_inert` re-asserts at S3-03 land.

## Notes for the implementer

1. **The land-time selection is the body of the work.** Do not punt it to a follow-up PR — `High-level-impl.md §"Implementation-level risks"` #3 explicitly calls out ADR-0003 drift as the failure mode. AC-15 pins the ADR edit; the PR-template checklist enforces it; the documentation-only test confirms the header pattern lands.
2. **Marker construction is positional-only.** Phase 0's `test_subclasses_are_markers_only` and S1-01's `test_phase1_subclasses_accept_message_arg_and_expose_args0` parametrize `MalformedLockfileError` and assert `not hasattr(exc, "path")`. Do **not** add a `MalformedLockfileError.__init__(self, *, path, cause)`. The path goes in `args[0]`; the cause goes on `__cause__` via `raise ... from cause`. Same discipline S1-02 / S1-03 / S3-01 / S3-02 settled.
3. **Use the shared `open_capped` kernel.** `parsers/_io.open_capped` is the single source of truth for `O_NOFOLLOW` + `os.fstat` size-cap. Do **not** reimplement either defense in this module. The `parser_kind="yarn_lockfile"` literal is yarn's contribution to the registry pattern; it surfaces on the structured `probe.parser.cap_exceeded` event (AC-18's test). `errno.ELOOP` portability is the kernel's problem, not yours.
4. **Strict UTF-8 decode.** `body.decode("utf-8")` without `errors="replace"` — Rule 12 (fail loud). Replacement-character substitution would let the scanner chase garbage and surface a confusing `ValueError` far from the real cause. Invalid bytes must surface as `UnicodeDecodeError` → `MalformedLockfileError` via the AC-7 translation path.
5. **The 60 MB size-cap test uses `os.fstat` monkey-patching, not a 60 MB write.** Mirror S3-01/S3-02 precedent. The kernel's `open_capped` checks `os.fstat(fd).st_size > max_bytes` before any `os.read`.
6. **Local fuzzing IS required before opening the PR.** `High-level-impl.md §"Implementation-level risks"` #4 names this: "adversarial fuzzing in S5-02 is the CI gate but not the first defense." A 1000-iteration loop with byte-mutated `yarn.lock` and a 1-second-per-iteration `signal.alarm` timeout is sufficient evidence; capture the worst-case wall-clock in the PR body. The script lives at `tools/fuzz_yarn_lock.py` so it isn't pytest-collected; the script targets `_parse_handrolled` directly (functional-core / imperative-shell pays off here — the pure function is testable without I/O).
7. **Rule of three — DEFER extraction (DP-1).** S3-03 is the **third** concrete lockfile-parser consumer of the family kernel, so the rule-of-three threshold is crossed. But the trio is two-of-a-kind (pnpm/npm — both wrap `safe_X.load`) plus one-of-a-kind (yarn — wraps `open_capped` directly, dispatches between `pyarn` and hand-rolled, catches `Exception` broadly). Extracting `_translate(path, *, cause)` would either (a) widen the helper to swallow `Exception`, loosening pnpm/npm's narrow `MalformedYAMLError`/`MalformedJSONError` catches, or (b) require two helpers, defeating the abstraction. CLAUDE.md Rule 2: "three similar lines is better than premature abstraction." **Documented; no helper extracted here.** Phase 2 can revisit if a fourth lockfile (`bun.lockb`) reveals the right shape.
8. **Open/Closed at the family level.** Adding a `_bun.py` later must require zero edits to `_yarn.py` (AC-17) or `_lockfiles/__init__.py` (AC-1). The shared kernel for the family is `parsers/_io.open_capped` + `codegenie.errors`, not other sibling modules.
9. **`_HAS_PYARN` is the strategy switch.** A two-strategy dispatch in its smallest form. Not refactored to a module-level `_PARSER_FN: Callable[[bytes], YarnLock]` binding because the call sites are simple enough that the indirection wouldn't pay for itself, and Rule 2 pre-empts the abstraction. If `pyarn` is ever joined by a second optional parser (e.g., a future `yarnberry` standalone library), revisit.
10. **Functional core / imperative shell.** `_parse_handrolled(body: bytes) -> YarnLock` and `_pyarn_parse(body: bytes) -> YarnLock` are pure — they operate on bytes, not paths. The only I/O function is `parse(path)`. This split is what makes the local fuzz harness (AC-16) testable: it targets `_parse_handrolled` directly with byte-mutated inputs, no filesystem involvement.
11. **Don't add a `pyarn` fall-back on parse-error path.** If `pyarn` is installed but fails on a real lockfile, that's a fixture portfolio issue worth surfacing (the parity test in S3-04 catches it). Silent fall-back muddies the parity contract. Arch §"Edge cases" row 10 explicitly scopes the fall-back to the `_HAS_PYARN=False` (uninstall) case, not the `_HAS_PYARN=True` + parse-error case.
12. **Multi-specifier keys.** `yarn.lock` can have a single header line like `"foo@^1.0, foo@^1.1":` covering multiple specifier ranges. The hand-rolled scanner currently keys on the entire line; `NodeManifestProbe` (S3-05) splits on `, ` when reconciling. Pinned in Out-of-scope.
13. **Borderline release-age decision.** If `pyarn`'s last release is exactly at the 18-month boundary (released on `2024-11-14`), default to hand-rolled and document the borderline decision in the ADR note. Rule 12 (Fail loud): a "close call" is a decision, not a deferral.
14. **`pyarn` API verification at land-time.** AC-13 is binding. Inspect `pyarn.__init__.py` and the PyPI page to confirm the actual call shape. The Green code sketches `pyarn.lockfile.Lockfile.from_string(...)` — verify this against the installed version; replace if wrong; record the verified shape in ADR-0003's land-time block. If the API doesn't fit the dispatch contract (body-bytes-in, `YarnLock`-out), the land-time selection flips to hand-rolled.
15. **Reversibility (per ADR-0003).** Switching parsers later is a `_HAS_PYARN` re-check (driven by `find_spec`, not a hardcoded flag) + a `pyproject.toml` edit; nothing in the cache / wire format depends on the parser identity. That property must remain true after this PR — if you find yourself adding parser-specific fields to `YarnLock`, stop.
16. **`fence` CI job stays green.** `pyarn` is not an LLM SDK; `fence` verifies `src/codegenie/` imports nothing from `openai`, `anthropic`, etc. Re-run `fence` locally before opening the PR per `High-level-impl.md §"Step 3" "Done criteria"` last line.
