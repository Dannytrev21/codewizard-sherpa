# Story S4-01 — `collect_build_signal` + `collect_install_signal`

**Step:** Step 4 — Six signal collectors + StrictAndGate adapter
**Status:** Ready (HARDENED 2026-05-24)
**Effort:** S
**Depends on:** S3-07 (DinD integration suite produces real `SandboxRun` artifacts), S1-05 (`@register_signal_kind` registry + delegation to Phase-3 `signal_kind_registry`), S1-03 (`ObjectiveSignals` + `BuildSignal` / `InstallSignal` sub-models + `SignalKind` newtype + `AwareDatetime` discipline)
**ADRs honored:** ADR-0003, ADR-0014, ADR-0015 (sibling test collector context only) + production [ADR-0001 hashing chokepoint](../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md)

## Validation notes (2026-05-24 — phase-story-validator)

Hardened via `phase-story-validator` (verdict: HARDENED). Source-of-truth
contradictions resolved against [`../phase-arch-design.md §Signal
collectors`](../phase-arch-design.md), [`../phase-arch-design.md §Data
model`](../phase-arch-design.md), [ADR-0003](../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md),
[ADR-0014](../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md),
the three sibling HARDENED reports (S1-02, S1-03, S1-05, S3-01), and the
**already-shipped** Phase 0 hashing chokepoint at
[`src/codegenie/hashing.py`](../../../../src/codegenie/hashing.py). Full
report: [`_validation/S4-01-build-install-collectors.md`](_validation/S4-01-build-install-collectors.md).

Headline edits (every weakness the four critics flagged would have let a
structurally-wrong implementation slip past the executor's validator):

1. **(coverage — block) `SignalProvenance.{signal_kind, collector_module,
   collector_version}` values pinned positively.** Draft asserted the field
   *existed* on the returned signal; it never asserted the *values*. A
   `build.py` copy-paste that mints `signal_kind="install"` passed every
   draft test. New AC-PROV-KIND-1..-2, AC-PROV-MODULE-1..-2, AC-PROV-VERSION-1
   + paired tests.
2. **(coverage — block) `at: AwareDatetime` enforced.** S1-03 AC-6 rejects
   naive `datetime` at construction; draft never asserted the collector
   produces a tz-aware `at`. A naive `datetime.utcnow()` would
   `ValidationError` on first run; the test plan didn't catch this. New
   AC-AT-TZ-1 + test case.
3. **(test-quality — block) Pure-function determinism test re-called the
   collector on the SAME `SandboxRun` instance.** Passes even for an impl
   that returns `f"blake3:{id(run):x}"`. The property the AC wants is
   *content* determinism: two equivalently-constructed but distinct
   instances produce byte-equal `inputs_blake3`. AC-DETERMINISM-1 rewrites
   the test to use two distinct `_run(...)` calls.
4. **(consistency — block) ADR-0001 hashing chokepoint violated.**
   Phase 0 ADR-0001 pins `codegenie.hashing` as the **single source of
   truth** for hashing — "no other file under `src/codegenie/` imports
   `blake3` or `hashlib.sha256`." Draft's `_inputs_blake3` helper implied a
   direct `blake3` import. New AC-HASH-CHOKEPOINT-1..-3 mandate delegation
   to `codegenie.hashing.content_hash_bytes` + AST scan asserting no
   `blake3` import under `sandbox/signals/`.
5. **(consistency — block) Canonical-JSON serialization specified.** Naive
   `json.dumps` is Python-minor-unstable (S3-01 flagged the same risk).
   AC-HASH-INPUTS-1 pins
   `json.dumps({...}, sort_keys=True, separators=(",", ":")).encode("utf-8")`.
6. **(consistency — block) Decorator-delegation to Phase 3 named.** S1-05
   HARDENED #1 establishes `@register_signal_kind` **delegates** the
   name-side to Phase-3's `signal_kind_registry` — and `"build"` /
   `"install"` are ALREADY pre-registered there per
   [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py).
   AC-REG-IDEMPOTENT-1 asserts both register without raising; new Notes
   paragraph names the delegation (Rule 7).
7. **(coverage — block) Import-time registration side-effect pinned.**
   Notes #3 said "package `__init__.py` must import them" — no AC enforced
   it. An executor skipping the re-export ships collectors that never
   appear in `signal_collector_registry`. AC-INIT-1..-2 pin both the
   re-export and the registry-resolution check.
8. **(coverage — harden) `details` value-set pinned exactly on the
   failure path** via a module-level `_BUILD_DETAIL_KEYS: Final[frozenset[str]]`
   catalog (S1-03 Notes pattern, S2's `_WARNING_IDS` precedent).
   AC-DETAILS-KEYS-1..-2.
9. **(coverage — harden) `last_log_line` truncation is 256 UTF-8 bytes**
   post `.decode("utf-8", errors="replace")`. An adversarial 256-emoji line
   is 1024 UTF-8 bytes; "chars" was ambiguous. AC-LASTLOG-TRUNC-1 +
   AC-LASTLOG-EMPTY-1.
10. **(coverage — harden) `passed=True` success-path `details` contract
    pinned** at `{"exit_code": 0}` (a minimum non-empty success signal —
    empty `{}` is ambiguous with "no information"). AC-DETAILS-PASS-1.
11. **(test-quality — harden) Hypothesis property test for the AND
    formula.** Four draft cases didn't cover the AND-formula exhaustively;
    the `and` → `or` mutation slipped past four of seven. AC-PROP-PASSED-1
    over `int × bool × bool`.
12. **(test-quality — harden) Cross-collector parity parametrized.**
    Draft said "mirror this file" for install — duplicates rot at different
    rates. AC-PARITY-1 introduces a single parametrized layer over
    `(collect, kind, model_cls)` covering both collectors uniformly. Sets
    the template for Phase 7's `baseimage` / `shell_presence`.
13. **(test-quality — harden) `SandboxSpec` test-fixture hash placeholder
    fixed.** Draft used `sandbox_spec_hash="deadbeef"` (8 chars); S3-01
    pins 32-char hex. AC-FIXTURE-HASH-1 mandates `"0" * 32`; a `conftest.py`
    helper `_make_run` is the single fixture chokepoint.
14. **(consistency — harden) Misleading Notes guidance removed.** Notes #1
    said "Convert any duration to int milliseconds; convert lists to
    comma-joined strings" — build/install `details` carry neither. Rewritten
    to scope to S4-02..S4-06.
15. **(patterns — harden) Strategy-helper extraction signposted at
    Phase-7 third no-extra-input collector — NOT here.** Rule-of-three for
    `_collect_simple(run, kind, model_cls)` hits at Phase 7 (`baseimage`,
    `shell_presence`), not S4-01 (only two instances, and S4-03 collectors
    all take extra kwargs so don't extend this shape). Notes paragraph #7
    documents the trigger.
16. **(patterns — harden) `SignalKind` newtype boundary.** AC-NEWTYPE-1
    pins that `signal_collector_registry.get(SignalKind("build"))` returns
    the registered function (matching S1-05 AC-CR-7).
17. **(consistency — harden) `datetime.now(timezone.utc)` (not `UTC` alias).**
    Codebase convention per S1-03; Rule 11.
18. **(consistency — harden) Registry test file ownership.** Story
    appends to S1-05's `tests/sandbox/test_signal_collector_registry.py`,
    not a new parallel `test_signals_registry.py` — avoids split test
    ownership of the same registry. AC-REG-TEST-1.
19. **(nit) Module docstring / `__all__` / `from __future__ import
    annotations` discipline mirrored from S1-02 / S1-03 / S1-05.** AC-DOC-1,
    AC-PURE-1, AC-PURE-2.

No `RESCUE`-tier findings. No Stage-3 research needed — every gap was
answerable from Phase 5 arch + ADRs + the four prior HARDENED reports
(S1-02, S1-03, S1-05, S3-01) + codebase precedents
([`codegenie.hashing`](../../../../src/codegenie/hashing.py),
[`transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py),
`probes/language_detection.py` Final-catalog pattern) + CLAUDE.md
load-bearing commitments (Extension by addition, Newtype identifiers,
Functional core / imperative shell, Rule 9, Rule 11). Goal, scope,
dependencies (S1-03, S1-05, S3-07), out-of-scope discipline, and ADR
mapping (-0003, -0014, +0001 chokepoint) are unchanged.

## Context

The two simplest of the six signal collectors. Each translates a `SandboxRun` produced by a real DinD execution of the `build` / `install` phase into a typed Pydantic sub-model. Build and install signals are pure functions over `run.exit_code`, `run.logs_dir`, and `run.timed_out` / `run.killed_by_oom` — no external resources, no diff baselines. This story is the template the remaining four collectors copy from; getting the shape right here pays back four times.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Signal collectors (six functions; open registry)` — function signatures, ≤ 60 LOC budget, "Returns the signal sub-model with `passed=False` and structured `details` reason; never raises".
- **Architecture:** `../phase-arch-design.md §Data model` — `_SignalBase`, `BuildSignal`, `InstallSignal`, `SignalProvenance`, the `details: dict[str, str | int | bool]` constraint (no float, no nested dict).
- **Phase ADRs:** `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — collectors register via `@register_signal_kind`; widens Phase 3's open kind registry.
- **Phase ADRs:** `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `details` keys are screened by the static introspection test; `confidence`/`llm`/`self_reported`/`model_says` substrings are banned.
- **High-level impl:** `../High-level-impl.md §Step 4` — each collector ≤ 60 LOC, decorated with `@register_signal_kind`.
- **Existing code:** `src/codegenie/sandbox/contract.py` (S1-02) — `SandboxRun` fields the collectors read.
- **Existing code:** `src/codegenie/sandbox/signals/models.py` (S1-03) — `BuildSignal`, `InstallSignal`, `_SignalBase`, `SignalProvenance`.
- **Existing code:** `src/codegenie/sandbox/signals/registry.py` (S1-05) — `@register_signal_kind` decorator; delegates the name-side to Phase 3's `signal_kind_registry`; collision policy.
- **Existing code:** [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py) — Phase 3 module that **already** pre-registers `"build"`, `"install"`, `"tests"`, `"trace"`, `"policy"`, `"cve_delta"` via `BUILD = register_signal_kind("build")` lines. Phase 5's `@register_signal_kind` decorator is idempotent on these existing names per S1-05 AC-COL-4.
- **Hashing chokepoint (ADR-0001):** [`src/codegenie/hashing.py`](../../../../src/codegenie/hashing.py) — `content_hash_bytes(b: bytes) -> str` is the **only** sanctioned BLAKE3 entry point; no other module imports `blake3` directly. The collector's `_inputs_blake3` helper MUST delegate to this chokepoint.
- **Sibling validation reports:** [`_validation/S1-02-sandbox-contract-protocol-models.md`](_validation/S1-02-sandbox-contract-protocol-models.md), [`_validation/S1-03-objective-signals-models.md`](_validation/S1-03-objective-signals-models.md), [`_validation/S1-05-registries-and-env-allowlist.md`](_validation/S1-05-registries-and-env-allowlist.md), [`_validation/S3-01-spec-builder-canonical-hash.md`](_validation/S3-01-spec-builder-canonical-hash.md) — pattern + naming + canonical-JSON precedents this story mirrors.

## Goal

Ship two pure-function signal collectors — `collect_build_signal(run: SandboxRun) -> BuildSignal` and `collect_install_signal(run: SandboxRun) -> InstallSignal` — each ≤ 60 LOC, decorated with `@register_signal_kind`, returning frozen sub-models whose `passed` field reflects `run.exit_code == 0 and not run.timed_out and not run.killed_by_oom`.

## Acceptance criteria

### A. Module surface, hygiene, and registration

- [ ] **AC-API-1** `src/codegenie/sandbox/signals/build.py` defines `collect_build_signal(run: SandboxRun) -> BuildSignal`, ≤ 60 LOC excluding imports/`__all__`, decorated `@register_signal_kind("build")`.
- [ ] **AC-API-2** `src/codegenie/sandbox/signals/install.py` defines `collect_install_signal(run: SandboxRun) -> InstallSignal`, ≤ 60 LOC, decorated `@register_signal_kind("install")`.
- [ ] **AC-DOC-1** Each module's first non-blank docstring paragraph references `ADR-0003`, `ADR-0014`, ADR-0001 (hashing chokepoint), and the source story `S4-01`. Asserted by AST scan over module source.
- [ ] **AC-PURE-1** Each module has `from __future__ import annotations` as the first non-docstring line.
- [ ] **AC-PURE-2** `set(codegenie.sandbox.signals.build.__all__) == {"collect_build_signal"}` and `set(codegenie.sandbox.signals.install.__all__) == {"collect_install_signal"}` (byte-exact; alphabetized trivially since single entry).
- [ ] **AC-PURE-3** `set(codegenie.sandbox.signals._common.__all__) == {"build_provenance", "inputs_blake3", "read_last_log_line", "utc_now"}` (the four shared helpers; module name carries the leading underscore — module-private; function names do NOT — cross-module reuse legit, mirrors S1-03's `_introspection.py` discipline).
- [ ] **AC-INIT-1** `src/codegenie/sandbox/signals/__init__.py` imports both `build` and `install` modules at package import time so that `@register_signal_kind` decorators fire. Asserted by AST scan of `__init__.py` finding `from . import build, install` (or equivalent).
- [ ] **AC-INIT-2** After `import codegenie.sandbox.signals`, the call `signal_collector_registry.get(SignalKind("build")) is collect_build_signal` returns `True`; same for `"install"`. Verifies registration side-effect actually fires.
- [ ] **AC-REG-IDEMPOTENT-1** Importing both `build.py` and `install.py` does NOT raise `codegenie.transforms.signal_kinds.SignalKindAlreadyRegistered` even though `"build"` and `"install"` are already pre-registered in Phase 3's `signal_kind_registry` per [`transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py). Tested by a pytest that constructs `SignalCollectorRegistry.fresh()`, then re-invokes the decorators against the fresh instance — no error. Closes S1-05 AC-COL-4 for the build/install case.
- [ ] **AC-NEWTYPE-1** `signal_collector_registry.get(SignalKind("build"))` (NewType-keyed lookup, not raw `str`) returns `collect_build_signal`; same for `SignalKind("install")`. Matches S1-05 AC-CR-7.
- [ ] **AC-REG-TEST-1** Registry-resolution assertions are added to the **existing** `tests/sandbox/test_signal_collector_registry.py` from S1-05 — NOT a new parallel `test_signals_registry.py` file. Avoids split test ownership of the same registry.

### B. `passed` formula (the strict-AND seed)

- [ ] **AC-PASSED-1** Both collectors compute `passed = (run.exit_code == 0 and not run.timed_out and not run.killed_by_oom)`. Asserted via the seven truth-table corners exercised in TDD (not just the four happy/sad cases the draft had).
- [ ] **AC-PROP-PASSED-1** Hypothesis property: `@given(exit_code=st.integers(), timed_out=st.booleans(), oom=st.booleans())` over both collectors — `collect_build_signal(_run(exit_code=ec, timed_out=t, oom=o)).passed == (ec == 0 and not t and not o)`. Catches the `and`→`or` and `==`→`!=` mutations the four-corner draft cases missed.

### C. `details` shape — failure path

- [ ] **AC-DETAILS-KEYS-1** On the failure path (`passed=False`), `set(sig.details.keys()) == _BUILD_DETAIL_KEYS` where `_BUILD_DETAIL_KEYS: Final[frozenset[str]] = frozenset({"exit_code", "timed_out", "killed_by_oom", "last_log_line"})` is a module-level catalog in `build.py` (S1-03 Notes pattern; precedent: `probes/language_detection.py`'s `_WARNING_IDS`). Mirror for install in `install.py` (`_INSTALL_DETAIL_KEYS`).
- [ ] **AC-DETAILS-KEYS-2** Catalog identity asserted by import: `from codegenie.sandbox.signals.build import _BUILD_DETAIL_KEYS` (single-underscore — module-private but test-accessible, mirrors S3-01 AC-INTERNAL-1 idiom).
- [ ] **AC-DETAILS-TYPES-1** Value types on the failure path: `type(d["exit_code"]) is int`, `type(d["timed_out"]) is bool`, `type(d["killed_by_oom"]) is bool`, `type(d["last_log_line"]) is str`. The `bool` ⊂ `int` ambiguity is closed via `type(v) is bool` identity (matches S1-03 AC-5a).
- [ ] **AC-DETAILS-NOBAN-1** No key in `_BUILD_DETAIL_KEYS` or `_INSTALL_DETAIL_KEYS` contains the substrings `confidence`, `llm`, `self_reported`, `model_says` (ADR-0014). Asserted via `iter_nested_field_names` walker re-run + a direct frozenset substring scan in the test (defense-in-depth: this story does NOT modify `ObjectiveSignals`, but the catalog values are evidence the fence stays green).

### D. `details` shape — success path

- [ ] **AC-DETAILS-PASS-1** On the success path (`passed=True`), `sig.details == {"exit_code": 0}` byte-exact. (Empty `{}` would be ambiguous with "no information collected"; a single key documents "we observed exit 0".)

### E. `last_log_line` truncation + IO discipline

- [ ] **AC-LASTLOG-TRUNC-1** `last_log_line` is the last non-empty line of `(logs_dir / "stdout.log")`, decoded as `bytes.decode("utf-8", errors="replace")`, then **truncated to 256 UTF-8 bytes** (NOT 256 code points — an adversarial 256-emoji line is 1024 UTF-8 bytes). Truncation is byte-safe: if a truncation falls mid-multibyte sequence, additional bytes are dropped until a valid UTF-8 prefix remains.
- [ ] **AC-LASTLOG-EMPTY-1** `last_log_line == ""` on each of: missing `logs_dir`, missing `stdout.log`, zero-length `stdout.log`, unreadable file (PermissionError), file containing only newlines. Collector NEVER raises on any of these.
- [ ] **AC-FCS-1** `_common.read_last_log_line(logs_dir: Path) -> str` is a pure (modulo file I/O) function with no module-level state; testable independently of any collector. Functional-core-imperative-shell separation: collectors are imperative (mint `at`, build provenance, decorate); the helper is the I/O.

### F. `SignalProvenance` value pinning

- [ ] **AC-PROV-KIND-1** `collect_build_signal(_run_passing()).provenance.signal_kind == SignalKind("build")`; same for install with `SignalKind("install")`.
- [ ] **AC-PROV-KIND-2** `type(sig.provenance.signal_kind) is str` (NewType's runtime identity is `str`; mypy-level `SignalKind` distinction is annotation-only — see S1-03 AC-4 / AC-4a).
- [ ] **AC-PROV-MODULE-1** `sig.provenance.collector_module == "codegenie.sandbox.signals.build"` byte-exact; mirror for install. (NOT `"sandbox.signals.build"`, NOT `"build"`, NOT `__name__.rsplit(".", 1)[0]`.)
- [ ] **AC-PROV-MODULE-2** AST scan of `build.py` source asserts the literal `"codegenie.sandbox.signals.build"` appears OR the source uses `__name__` directly (then the test asserts `sig.provenance.collector_module == __name__`).
- [ ] **AC-PROV-VERSION-1** `sig.provenance.collector_version == "1"` byte-exact (string, NOT int). A bump is an ADR amendment per arch §Signal collectors.

### G. `inputs_blake3` — hashing chokepoint discipline (ADR-0001)

- [ ] **AC-HASH-CHOKEPOINT-1** `_common.inputs_blake3(run: SandboxRun) -> str` delegates to `codegenie.hashing.content_hash_bytes(...)`. AST scan of `_common.py` source asserts `from codegenie.hashing import content_hash_bytes` is present AND `import blake3` / `from blake3 import ...` is ABSENT.
- [ ] **AC-HASH-CHOKEPOINT-2** AST scan over all of `src/codegenie/sandbox/signals/**/*.py` asserts NO module imports `blake3` directly OR `hashlib.sha256`. Phase 0 ADR-0001 chokepoint discipline preserved.
- [ ] **AC-HASH-CHOKEPOINT-3** Return value matches `codegenie.hashing.content_hash_bytes` shape: `blake3:<64-hex>` (prefix-tagged, lowercase hex). Asserted via regex `^blake3:[0-9a-f]{64}$` over the returned string.
- [ ] **AC-HASH-INPUTS-1** Canonical-JSON shape of the hash input is exactly:
  ```python
  json.dumps(
      {"run_id": run.run_id, "spec_hash": run.spec.sandbox_spec_hash, "exit_code": run.exit_code},
      sort_keys=True,
      separators=(",", ":"),
  ).encode("utf-8")
  ```
  Pinned positively: a golden test asserts that for a fixed `SandboxRun`, the helper's output equals `content_hash_bytes(<the exact bytes above>)`. Catches drift to non-sort-keyed `json.dumps`, to a different separators tuple, or to a different key set.
- [ ] **AC-HASH-INPUTS-2** Hash input does NOT include `run.spec` in full (only the spec hash) — keeps the input bounded regardless of how `SandboxSpec` evolves; `sandbox_spec_hash` is already content-addressed.
- [ ] **AC-DETERMINISM-1** **Two distinct `SandboxRun` instances** constructed with identical kwargs (different Python `id()`) produce **byte-equal** `provenance.inputs_blake3`. Test rewrites the draft's `collect_build_signal(run); collect_build_signal(run)` pattern (same-instance — passes even for `id(run)`-based impls) to `collect_build_signal(_run(...)); collect_build_signal(_run(...))` with two distinct calls to the fixture factory.

### H. Timezone-aware `at` (ADR-0014 / S1-03)

- [ ] **AC-AT-TZ-1** `sig.at.tzinfo is not None` AND `sig.at.tzinfo.utcoffset(sig.at).total_seconds() == 0` (UTC, not just "any tzinfo"). Verifies `_common.utc_now()` uses `datetime.now(timezone.utc)` per S1-03 AC-6/AC-6a and codebase convention.
- [ ] **AC-AT-TZ-2** AST scan of `_common.py` source asserts `from datetime import datetime, timezone` is present AND `datetime.utcnow(` is ABSENT (`utcnow` returns naive datetime — Python deprecated it in 3.12, would silently `ValidationError` against `AwareDatetime`).

### I. Cross-collector parity (template for Phase 7)

- [ ] **AC-PARITY-1** The seven core invariants in §B/§C/§D/§F/§G/§H are exercised via a SINGLE parametrized test layer:
  ```python
  @pytest.mark.parametrize(
      "collect,kind,model_cls,details_keys",
      [
          (collect_build_signal, "build", BuildSignal, _BUILD_DETAIL_KEYS),
          (collect_install_signal, "install", InstallSignal, _INSTALL_DETAIL_KEYS),
      ],
  )
  ```
  Mirroring duplicated test files is forbidden by this AC (Rule 3 — surgical, not parallel-rot prone). Sets the template that S4-02..S4-06 and Phase-7 collectors extend by adding a row.
- [ ] **AC-FIXTURE-HASH-1** `conftest.py` (or a single helper module under `tests/sandbox/`) exposes `_make_run(...)` as the single SandboxSpec/Run fixture factory; `sandbox_spec_hash="0" * 32` (32-char hex placeholder matching S3-01 AC-HASH-FORMAT). Both collector test files import from this conftest; ad-hoc `SandboxSpec.model_construct(..., sandbox_spec_hash="deadbeef")` is forbidden by an AST-scan test under `tests/sandbox/test_signals_fixture_hash_discipline.py`.

### J. Failure-mode discipline (never raises)

- [ ] **AC-NEVER-RAISES-1** Collectors NEVER raise on collector-specific failure: missing `logs_dir`, missing `stdout.log`, unreadable `stdout.log` (PermissionError), `logs_dir` is a symlink loop, `logs_dir` is a file (not directory). Each surfaced as `passed=False` with `details["last_log_line"] == ""` AND the other three keys reflecting `run`'s observed state.
- [ ] **AC-NEVER-RAISES-2** Collectors raise `TypeError` ONLY on programming errors (e.g., wrong type passed for `run`). This is the contract per arch §Failure behavior — "never raises on collector-specific failures."

### K. Fence preservation

- [ ] **AC-FENCE-1** `tests/schema/test_objective_signals_static.py` still green — no banned substring entered the type tree. (This story does NOT modify `ObjectiveSignals`; `_BUILD_DETAIL_KEYS` / `_INSTALL_DETAIL_KEYS` are module-level catalogs that the walker doesn't traverse, but the catalog's own values are screened by AC-DETAILS-NOBAN-1.)

### L. Quality gates

- [ ] **AC-PG-1** `ruff check`, `ruff format --check`, `mypy --strict` pass on `src/codegenie/sandbox/signals/{_common,build,install,__init__}.py`.
- [ ] **AC-PG-2** Coverage on touched files: **line ≥ 95% AND branch ≥ 90%** (matches phase README definition-of-done; sibling S1-02 #12 fixes the previous "≥ 95% branch" wording bug).
- [ ] **AC-PG-3** TDD plan's red test exists in commit history (separate commit before the green commit), is committed, and is green at the end of the story.

## Implementation outline

1. Create `src/codegenie/sandbox/signals/_common.py` (the shared helper module — extracted up front because BOTH `build.py` AND `install.py` need all four helpers; this is rule-of-three-by-anticipation at two collectors only because the helpers are 1-call-site-per-collector pure utilities, not a Strategy abstraction):
   - `from __future__ import annotations` (line 1 post-docstring); module docstring cites ADR-0003, ADR-0014, ADR-0001, and source story S4-01.
   - `from datetime import datetime, timezone` (NOT `from datetime import UTC` — see AC-AT-TZ-2 + Rule 11).
   - `from codegenie.hashing import content_hash_bytes` (the ADR-0001 chokepoint — NOT `import blake3`).
   - `def read_last_log_line(logs_dir: Path) -> str`: opens `logs_dir / "stdout.log"`, reads as bytes, splits on `b"\n"`, finds the last non-empty line, decodes with `errors="replace"`, truncates to 256 UTF-8 bytes (byte-safe — drop trailing partial-multibyte). Returns `""` on missing dir / missing file / zero-length / PermissionError / IsADirectoryError / OSError.
   - `def inputs_blake3(run: SandboxRun) -> str`: builds the canonical-JSON payload per AC-HASH-INPUTS-1 (`sort_keys=True, separators=(",", ":")`) and calls `content_hash_bytes(...)`.
   - `def build_provenance(*, signal_kind: SignalKind, collector_module: str, run: SandboxRun) -> SignalProvenance`: factory; pins `collector_version="1"` and computes `inputs_blake3` via the helper above.
   - `def utc_now() -> datetime`: returns `datetime.now(timezone.utc)`. Sole concentration point for "now" — Phase 9 can monkeypatch for replay.
   - `__all__ = ["build_provenance", "inputs_blake3", "read_last_log_line", "utc_now"]` (alphabetized).
2. Create `src/codegenie/sandbox/signals/build.py`:
   - `from __future__ import annotations`; module docstring per AC-DOC-1.
   - `_BUILD_DETAIL_KEYS: Final[frozenset[str]] = frozenset({"exit_code", "timed_out", "killed_by_oom", "last_log_line"})`.
   - `from codegenie.sandbox.signals._common import build_provenance, read_last_log_line, utc_now`
   - `from codegenie.sandbox.signals.registry import register_signal_kind`
   - `@register_signal_kind("build")` `def collect_build_signal(run: SandboxRun) -> BuildSignal:` — pure computation of `passed`; builds `details` per §C/§D; constructs `BuildSignal(passed=..., details=..., provenance=build_provenance(signal_kind=SignalKind("build"), collector_module=__name__, run=run), at=utc_now())`.
   - `__all__ = ["collect_build_signal"]`.
3. Create `src/codegenie/sandbox/signals/install.py` — identical shape with `_INSTALL_DETAIL_KEYS` + `"install"` kind + `InstallSignal` model class. **Do NOT extract a `_collect_simple(run, kind, model_cls)` helper now** — rule-of-three is not met (only two instances; S4-03 collectors take extra kwargs so don't extend this shape). Phase-7 `baseimage`/`shell_presence` will trigger the extraction (Notes #7).
4. Update `src/codegenie/sandbox/signals/__init__.py` to `from . import build, install` so decorators fire at package import time (AC-INIT-1).
5. Add a SINGLE `tests/sandbox/conftest.py` (or extend the existing one if S3-01 already added one) exporting `_make_run(...)` as the chokepoint fixture factory per AC-FIXTURE-HASH-1.
6. Add `tests/sandbox/test_signals_collectors.py` — the parametrized layer (NOT separate `test_signals_build.py` + `test_signals_install.py` per AC-PARITY-1).
7. APPEND registry-resolution assertions to the **existing** `tests/sandbox/test_signal_collector_registry.py` (S1-05) — do NOT create a new `test_signals_registry.py` (AC-REG-TEST-1).
8. Add `tests/sandbox/test_signals_fixture_hash_discipline.py` (AST scan asserting no inline `sandbox_spec_hash=` with a value != `"0" * 32` under `tests/sandbox/` — keeps the fixture chokepoint single-source).
9. Run `tests/schema/test_objective_signals_static.py` to confirm AC-FENCE-1.

## TDD plan — red / green / refactor

### Red — write the failing test first

The test plan is intentionally a SINGLE parametrized layer over both
collectors (AC-PARITY-1) plus three structural files. Mirroring duplicate
test files is forbidden — duplicate test files rot at different rates and
fork the implementation contract.

#### Shared fixture chokepoint — `tests/sandbox/conftest.py` (extend if exists)

```python
# tests/sandbox/conftest.py  (extend or create — single SandboxRun factory)
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from codegenie.sandbox.contract import CopyInEntry, SandboxRun, SandboxSpec

# AC-FIXTURE-HASH-1 — 32-char hex placeholder matching S3-01 AC-HASH-FORMAT.
_PLACEHOLDER_HASH = "0" * 32


@pytest.fixture
def _make_run(tmp_path: Path):
    """Single fixture factory for SandboxRun across all collector tests.

    Why: ad-hoc per-test fixtures drift from the SandboxSpec/Run contract
    (S1-02 / S3-01). Single chokepoint = single point of update when the
    contract evolves.
    """

    def _factory(
        *,
        exit_code: int = 0,
        timed_out: bool = False,
        oom: bool = False,
        stdout: str = "npm WARN deprecated\nbuild output\n",
        logs_dir: Path | None = None,
        run_id: str = "01HXYZABCDEFGHJKMNPQRSTVWX",
    ) -> SandboxRun:
        if logs_dir is None:
            logs_dir = tmp_path / "logs"
            logs_dir.mkdir(exist_ok=True)
            (logs_dir / "stdout.log").write_bytes(stdout.encode("utf-8"))
        ts = datetime(2026, 5, 12, tzinfo=timezone.utc)
        spec = SandboxSpec.model_construct(
            base_image="cgr.dev/chainguard/node@sha256:abc",
            copy_in=[],
            env={},
            cmd=["npm", "run", "build"],
            network="none",
            egress_allowlist=[],
            enable_trace=False,
            time_budget_seconds=600,
            memory_limit_mib=2048,
            pids_limit=1024,
            copy_out=[],
            label="stage6.build.attempt1",
            sandbox_spec_hash=_PLACEHOLDER_HASH,
        )
        return SandboxRun.model_construct(
            run_id=run_id,
            spec=spec,
            backend="docker_in_docker",
            gate_isolation_class="shared_kernel",
            started_at=ts,
            ended_at=ts,
            exit_code=exit_code,
            duration_ms=1000,
            microvm_seconds=0.0,
            image_pull_bytes=0,
            build_cache_hit=True,
            logs_dir=logs_dir,
            trace_path=None,
            copy_out_root=tmp_path / "out",
            timed_out=timed_out,
            killed_by_oom=oom,
        )

    return _factory
```

#### Parametrized collector tests — `tests/sandbox/test_signals_collectors.py`

```python
# tests/sandbox/test_signals_collectors.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from codegenie.hashing import content_hash_bytes
from codegenie.sandbox.signals.build import _BUILD_DETAIL_KEYS, collect_build_signal
from codegenie.sandbox.signals.install import (
    _INSTALL_DETAIL_KEYS,
    collect_install_signal,
)
from codegenie.sandbox.signals.models import BuildSignal, InstallSignal
from codegenie.sandbox.signals.registry import signal_collector_registry
from codegenie.types.identifiers import SignalKind


CASES = [
    pytest.param(
        collect_build_signal,
        "build",
        BuildSignal,
        _BUILD_DETAIL_KEYS,
        "codegenie.sandbox.signals.build",
        id="build",
    ),
    pytest.param(
        collect_install_signal,
        "install",
        InstallSignal,
        _INSTALL_DETAIL_KEYS,
        "codegenie.sandbox.signals.install",
        id="install",
    ),
]


# AC-PASSED-1 — seven truth-table corners (exhaustive over exit_code∈{0,1} × t × o)
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
@pytest.mark.parametrize("exit_code", [0, 1, 137])
@pytest.mark.parametrize("timed_out", [False, True])
@pytest.mark.parametrize("oom", [False, True])
def test_passed_is_and_of_three_run_conditions(
    _make_run, collect, kind, model_cls, keys, module, exit_code, timed_out, oom
):
    # WHY: strict-AND seed. The 'and'->'or' mutation must fail on at least one corner.
    sig = collect(_make_run(exit_code=exit_code, timed_out=timed_out, oom=oom))
    expected = exit_code == 0 and not timed_out and not oom
    assert sig.passed is expected
    assert isinstance(sig, model_cls)


# AC-DETAILS-PASS-1 — success-path details contract
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_success_path_details_is_only_exit_code_zero(
    _make_run, collect, kind, model_cls, keys, module
):
    sig = collect(_make_run(exit_code=0))
    assert sig.passed is True
    assert sig.details == {"exit_code": 0}


# AC-DETAILS-KEYS-1 — failure-path details key set is the catalog
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_failure_path_details_keys_equal_catalog(
    _make_run, collect, kind, model_cls, keys, module
):
    sig = collect(_make_run(exit_code=1))
    assert sig.passed is False
    assert set(sig.details.keys()) == set(keys)


# AC-DETAILS-TYPES-1 — bool vs int identity (closes the bool⊂int ambiguity)
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_failure_path_details_value_type_identity(
    _make_run, collect, kind, model_cls, keys, module
):
    sig = collect(_make_run(exit_code=2, oom=True))
    assert type(sig.details["exit_code"]) is int
    assert type(sig.details["timed_out"]) is bool
    assert type(sig.details["killed_by_oom"]) is bool
    assert type(sig.details["last_log_line"]) is str


# AC-DETAILS-NOBAN-1 — defense-in-depth substring scan over the catalog
@pytest.mark.parametrize("keys", [_BUILD_DETAIL_KEYS, _INSTALL_DETAIL_KEYS])
@pytest.mark.parametrize("banned", ["confidence", "llm", "self_reported", "model_says"])
def test_detail_catalog_keys_contain_no_banned_substring(keys, banned):
    assert not any(banned in k for k in keys)


# AC-PROV-KIND-1 / AC-PROV-MODULE-1 / AC-PROV-VERSION-1 — provenance value pinning
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_provenance_values_pinned(
    _make_run, collect, kind, model_cls, keys, module
):
    sig = collect(_make_run(exit_code=0))
    assert sig.provenance.signal_kind == kind
    assert sig.provenance.collector_module == module
    assert sig.provenance.collector_version == "1"


# AC-NEWTYPE-1 / AC-INIT-2 — registry resolves the collector by SignalKind
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_registry_resolves_collector(collect, kind, model_cls, keys, module):
    assert signal_collector_registry.get(SignalKind(kind)) is collect


# AC-DETERMINISM-1 — TWO DISTINCT instances, same content → same blake3
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_inputs_blake3_is_content_deterministic_across_distinct_instances(
    _make_run, collect, kind, model_cls, keys, module
):
    # WHY: re-calling on the same instance (the draft pattern) passes even
    # for an impl that derives the hash from id(run). The property is content-
    # determinism: two distinct equally-constructed instances → byte-equal hash.
    a = collect(_make_run(exit_code=0))
    b = collect(_make_run(exit_code=0))
    assert a.provenance.inputs_blake3 == b.provenance.inputs_blake3


# AC-HASH-INPUTS-1 / AC-HASH-CHOKEPOINT-3 — golden canonical-JSON shape
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_inputs_blake3_matches_canonical_json_chokepoint_golden(
    _make_run, collect, kind, model_cls, keys, module
):
    run = _make_run(exit_code=0)
    expected_payload = json.dumps(
        {
            "run_id": run.run_id,
            "spec_hash": run.spec.sandbox_spec_hash,
            "exit_code": run.exit_code,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected = content_hash_bytes(expected_payload)
    sig = collect(run)
    assert sig.provenance.inputs_blake3 == expected
    assert re.fullmatch(r"blake3:[0-9a-f]{64}", sig.provenance.inputs_blake3)


# AC-AT-TZ-1 — at is UTC, not naive
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_at_is_timezone_aware_utc(_make_run, collect, kind, model_cls, keys, module):
    sig = collect(_make_run(exit_code=0))
    assert sig.at.tzinfo is not None
    assert sig.at.tzinfo.utcoffset(sig.at).total_seconds() == 0


# AC-NEVER-RAISES-1 — variety of IO failures on logs_dir all surface as last_log_line=""
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_never_raises_on_missing_logs_dir(
    _make_run, tmp_path, collect, kind, model_cls, keys, module
):
    run = _make_run(exit_code=1, logs_dir=tmp_path / "definitely_missing")
    sig = collect(run)
    assert sig.passed is False
    assert sig.details["last_log_line"] == ""


@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_never_raises_on_empty_stdout_log(
    _make_run, tmp_path, collect, kind, model_cls, keys, module
):
    logs = tmp_path / "empty_logs"
    logs.mkdir()
    (logs / "stdout.log").write_bytes(b"")
    run = _make_run(exit_code=1, logs_dir=logs)
    sig = collect(run)
    assert sig.details["last_log_line"] == ""


# AC-LASTLOG-TRUNC-1 — 256 UTF-8 BYTES (not 256 code points) — adversarial emoji
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
def test_last_log_line_truncated_to_256_utf8_bytes(
    _make_run, tmp_path, collect, kind, model_cls, keys, module
):
    logs = tmp_path / "fat_logs"
    logs.mkdir()
    # 100 emoji × 4 bytes/emoji = 400 UTF-8 bytes, well over 256
    line = "💥" * 100
    (logs / "stdout.log").write_text(f"prelude\n{line}\n", encoding="utf-8")
    run = _make_run(exit_code=1, logs_dir=logs)
    sig = collect(run)
    last = sig.details["last_log_line"]
    assert len(last.encode("utf-8")) <= 256
    # No partial-multibyte at the boundary — decode round-trips cleanly.
    assert last.encode("utf-8").decode("utf-8") == last


# AC-PROP-PASSED-1 — Hypothesis over (exit_code, timed_out, oom)
@pytest.mark.parametrize("collect,kind,model_cls,keys,module", CASES)
@given(
    exit_code=st.integers(min_value=-1, max_value=255),
    timed_out=st.booleans(),
    oom=st.booleans(),
)
def test_passed_formula_hypothesis(
    _make_run, collect, kind, model_cls, keys, module, exit_code, timed_out, oom
):
    sig = collect(_make_run(exit_code=exit_code, timed_out=timed_out, oom=oom))
    assert sig.passed is (exit_code == 0 and not timed_out and not oom)
```

#### Structural fence tests (AST scans — fail-loud on regressions)

`tests/sandbox/test_signals_purity.py` — asserts (a) `_common.py` imports
`content_hash_bytes` from `codegenie.hashing` AND does NOT import `blake3`
or `hashlib.sha256` (AC-HASH-CHOKEPOINT-1 + -2 + AC-HASH-CHOKEPOINT-2 over
all `signals/**/*.py`); (b) `_common.py` imports `timezone` from `datetime`
and does NOT contain `utcnow` (AC-AT-TZ-2); (c) `build.py` / `install.py`
each declare `_BUILD_DETAIL_KEYS` / `_INSTALL_DETAIL_KEYS` as
`Final[frozenset[str]]`; (d) module docstrings cite the three ADRs + S4-01.

`tests/sandbox/test_signals_fixture_hash_discipline.py` — AST scan over
`tests/sandbox/**/*.py` asserting no `keyword(arg="sandbox_spec_hash", value
!= "0" * 32)` outside `conftest.py` (AC-FIXTURE-HASH-1).

`tests/sandbox/test_signal_collector_registry.py` — APPEND (do NOT create
new) two test cases asserting AC-NEWTYPE-1 / AC-INIT-2 for `"build"` and
`"install"` post-`import codegenie.sandbox.signals`.

### Green — make it pass

- Land `_common.py` first; all four helpers unit-testable in isolation.
- Land `build.py`, `install.py`, and `__init__.py` together (registration
  side-effect must be atomic with the collectors).
- Verify the parametrized suite passes on both `build` and `install` rows
  before declaring green.

### Refactor — clean up

- Verify each public collector is ≤ 60 LOC (AC-API-1 / AC-API-2).
- Verify `_common.py` helpers each have a single docstring sentence
  describing the contract (no over-documentation per CLAUDE.md "default to
  writing no comments").
- Do **NOT** extract `_collect_simple(run, kind, model_cls)` in this story
  — rule-of-three is not met (Notes #7).

## Files to touch

| Path | Action | Why |
|---|---|---|
| `src/codegenie/sandbox/signals/_common.py` | create | Shared helpers — `read_last_log_line` (I/O — last-log reader), `inputs_blake3` (delegates to `codegenie.hashing.content_hash_bytes`), `build_provenance` (`SignalProvenance` factory), `utc_now`. Module-private filename; public function names per AC-PURE-3. |
| `src/codegenie/sandbox/signals/build.py` | create | Collector for `"build"` kind. Defines `_BUILD_DETAIL_KEYS: Final[frozenset[str]]` catalog. |
| `src/codegenie/sandbox/signals/install.py` | create | Collector for `"install"` kind. Defines `_INSTALL_DETAIL_KEYS: Final[frozenset[str]]` catalog. |
| `src/codegenie/sandbox/signals/__init__.py` | modify | Append `from . import build, install` so decorators fire at package import time (AC-INIT-1). |
| `tests/sandbox/conftest.py` | modify-or-create | Single SandboxRun fixture factory `_make_run` (AC-FIXTURE-HASH-1). |
| `tests/sandbox/test_signals_collectors.py` | create | The parametrized layer over both collectors (AC-PARITY-1). |
| `tests/sandbox/test_signals_purity.py` | create | AST-scan fences: hashing chokepoint (AC-HASH-CHOKEPOINT-1..-2), no `utcnow` (AC-AT-TZ-2), `Final[frozenset[str]]` catalogs, docstring ADR citations. |
| `tests/sandbox/test_signals_fixture_hash_discipline.py` | create | AST-scan asserting no `sandbox_spec_hash` literal outside `conftest.py` deviates from `"0" * 32` (AC-FIXTURE-HASH-1). |
| `tests/sandbox/test_signal_collector_registry.py` | modify (append) | Add AC-NEWTYPE-1 / AC-INIT-2 assertions. Do NOT create a parallel `test_signals_registry.py` (AC-REG-TEST-1). |

## Out of scope

- `collect_test_signal` — S4-02.
- Trace, policy, cve_delta collectors — S4-03.
- The `StrictAndGate` adapter — S4-05.
- `TrustScorer` widening — S4-04.
- Strategy-helper extraction `_collect_simple(run, kind, model_cls)` — defer to Phase 7's third no-extra-input collector (`baseimage` or `shell_presence`); rule-of-three is not met at two collectors and S4-03 collectors do not extend this shape.

## Notes for the implementer

1. **`details` value-types are strict primitives only.** ADR-0014 + S1-03 AC-5 — `dict[str, str | int | bool]`. Pydantic v2 strict mode rejects `float`, `None`, `list`, nested `dict` at construction. For build/install **this never matters** — the only values are `exit_code: int`, `timed_out: bool`, `killed_by_oom: bool`, `last_log_line: str`. (The "convert durations to ms / lists to comma-joined" guidance applies to S4-02 `TestSignal` where `failing_tests` is a comma-joined string and `delta_test_count` is an int — NOT here.)
2. **Hashing chokepoint (ADR-0001).** `_inputs_blake3` MUST delegate to `codegenie.hashing.content_hash_bytes(canonical_json_bytes)`. Do NOT `import blake3` directly. `tests/sandbox/test_signals_purity.py` enforces this via AST scan over `signals/**/*.py`.
3. **Decorator delegation to Phase 3 — `"build"` and `"install"` are pre-registered.** Per S1-05 HARDENED #1 + AC-COL-4, Phase 5's `@register_signal_kind("build")` decorator detects that `"build"` is already in Phase 3's `signal_kind_registry` (registered there by `BUILD = register_signal_kind("build")` at module-import) and **skips** the Phase 3 `register_signal_kind` call to avoid `SignalKindAlreadyRegistered`. You do NOT need to do anything special — the decorator handles it. AC-REG-IDEMPOTENT-1 catches a regression.
4. **Registration side-effect — `__init__.py` MUST import both modules.** The `@register_signal_kind` decorator runs at module-import time; if the package's `__init__.py` never imports `build` and `install`, `signal_collector_registry` is empty when `StrictAndGate` (S4-05) tries to resolve the collectors. AC-INIT-1 + AC-INIT-2 catch this.
5. **`SignalProvenance.collector_module` MUST be the actual `__name__`.** Use `__name__` (which evaluates to `"codegenie.sandbox.signals.build"` at runtime) — NOT a hardcoded string. The test asserts byte-equality with the literal module path (AC-PROV-MODULE-1).
6. **`SignalProvenance.collector_version = "1"` (string, NOT int).** ADR amendment required to bump. AC-PROV-VERSION-1 pins the literal.
7. **Strategy helper extraction is deferred to Phase 7.** Build and install are the FIRST two no-extra-input collectors. S4-03's three collectors (trace, policy, cve_delta) all take extra kwargs — they do NOT extend this exact shape. The third no-extra-input collector lands in Phase 7 (`baseimage` and/or `shell_presence` per arch §Goal 9 + ADR-0003 §Consequences). When Phase 7 implementers add the third instance, extract `_collect_simple(run, *, kind: SignalKind, model_cls: type[_SignalBase], module_name: str) -> _SignalBase` into `_common.py` as a Strategy/Template helper. Until then, two near-identical files are cleaner than a premature abstraction (Rule 2; CLAUDE.md "three similar lines is better than premature abstraction").
8. **`datetime.now(timezone.utc)` — NOT `datetime.now(UTC)` alias.** Codebase convention (Rule 11, S1-03 precedent). AC-AT-TZ-2's AST scan catches drift.
9. **Don't peek at logs to infer success.** `exit_code`, `timed_out`, `killed_by_oom` are the contract. `last_log_line` is annotation only — it goes into `details` but is NOT consulted by the `passed` formula.
10. **Run `tests/schema/test_objective_signals_static.py` locally before pushing.** A new banned substring fails the gate CI for the whole repo. This story does NOT modify `ObjectiveSignals` so the fence should pass trivially — but AC-DETAILS-NOBAN-1 is the in-story defense-in-depth on the catalog keys themselves.
11. **`last_log_line` truncation is byte-safe at 256 UTF-8 bytes.** Adversarial 256-emoji line = 1024 UTF-8 bytes. A naive `[:256]` slice on `str` would let through 1024 bytes; a naive `[:256]` slice on `bytes` could split a multibyte sequence. Use either `safe_truncate(s: str, max_bytes: int) -> str` that drops trailing bytes until valid UTF-8, OR encode → slice → decode with `errors="replace"`. AC-LASTLOG-TRUNC-1's test catches both failure modes.
