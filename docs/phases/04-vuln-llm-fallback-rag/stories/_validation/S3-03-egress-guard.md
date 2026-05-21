# Validation report: S3-03 — `EgressGuard` via `sitecustomize`

**Validated:** 2026-05-21
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S3-03's goal is sound and traces cleanly to ADR-0005 (no SPKI pin; `EgressGuard` is
defense-in-depth layer 1) and ADR-0006 (loopback rejected in production; pytest-fixture
thread-scoped opt-in). The draft was detailed and mostly executor-ready, but six gaps
would have caused executor failure, a silent unmet goal, or a divergence from hardened
S3-02. All six are fixed in place; eight further criteria were strengthened. No
structural rewrite was needed — verdict **HARDENED**.

## Process note

Per the four-critic workflow, the coverage / test-quality / consistency /
design-patterns lenses were applied. Given the scheduled-task autonomy context and the
token budget (global Rule 6), the four lenses were run as a single consolidated
synthesis by the validator rather than four spawned subagents — every lens is
represented in the findings below, each backed by a concrete file read
(`cli.py`, `__main__.py`, `pyproject.toml`, the S3-02 story + its `_validation` report,
ADR-0005, ADR-0006, `phase-arch-design.md`, the `tests/` tree).

## Context brief

### Story snapshot
- **Goal:** Install a process-wide `socket.create_connection` wrapper admitting only
  `api.anthropic.com:443`, with an `async` `pinned_to(host)` re-affirmation context
  manager, loopback rejected in production unless a pytest-fixture-set `ContextVar` is
  set, `reset_for_test()` cleanup, and a `codegenie self-check egress` reporting
  subcommand.
- **Non-goals:** OS-level filter enforcement, nightly drift job, C-extension
  `connect(2)` bypass, second host, `bootstrap_runtime()` move, wheel-install coverage.

### Phase / arch constraints
- ADR-0005: system trust store, no SPKI pin; allowlist is `api.anthropic.com:443`;
  defense-in-depth of four named layers.
- ADR-0006: loopback rejected by default; the *only* opt-in is a pytest-fixture-set
  thread-scoped flag — no env-var, no boolean param, no module constant.
- `phase-arch-design.md §Component 15` / `§Anti-patterns avoided`: the `sitecustomize`
  import-time install is an *acknowledged residual* with a Phase-5+ `bootstrap_runtime()`
  follow-up (§gap-analysis #2).

### Existing-code reality (the source of most findings)
- The CLI is **click**-based (`cli = @click.group`); `main(argv) -> int` lives in
  `codegenie.__main__`, **not** `codegenie.cli`.
- `tests/conftest.py` does **not** exist; the codebase has per-directory conftests.
- The adversarial-test convention is `tests/adv/` with per-phase subdirs
  (`tests/adv/phase02/`, marker `phase02_adv`) — **not** `tests/adversarial/`.
- `src/codegenie/fallback/` does not exist yet (S3-02 creates `fallback/leaf/`).
- Hardened S3-02 introduced a local `EgressGuardPort(Protocol)` —
  `pinned_to(host: str) -> AsyncContextManager[None]` — *specifically so S3-03 could
  satisfy it later* (S3-02 validation finding C3).

### Open ambiguities
None requiring user input — every conflict was resolvable against the built codebase
and hardened S3-02.

## Findings

### Blockers (fixed)

- **B1 — Coverage: the load-bearing mechanism was untested.** Every adversarial test
  installs the guard via an explicit `EgressGuard.install()` autouse fixture. The whole
  point of S3-03 — process-wide auto-install via `sitecustomize.py` — would therefore be
  green even if `sitecustomize.py` were never discovered. *Fix:* added **AC-26**, a
  subprocess test launching a fresh interpreter (`python -m codegenie self-check egress`,
  no explicit `install()`) and asserting `installed=True`; added a fail-loud Notes
  paragraph (do not delete the AC if it fails — switch bootstrap mechanism).
- **B2 — Coverage: process-wide blast radius unaddressed.** Committing `sitecustomize.py`
  makes *every* `pytest` / `python -m codegenie` run install the guard. No AC required
  the pre-existing ~2,300-test suite to stay green. *Fix:* added **AC-25** — the executor
  runs `make test` (whole suite), adds `egress_test_loopback` to legitimate loopback
  tests, surfaces any non-loopback external dial loudly (Rule 12).
- **B3 — Consistency/Test-Quality: `pinned_to` sync/async contradiction.** S3-02's
  `EgressGuardPort` requires an `AsyncContextManager`; story AC-11 uses `async with`; but
  the TDD red test `test_pinned_to_other_host_raises` used a **sync** `with`. An executor
  following the TDD plan literally would build a sync CM and break S3-02. *Fix:* TDD test
  rewritten to `async def` + `async with`; AC-1 / implementation outline now say "async
  context manager" explicitly.
- **B4 — Consistency: the S3-02 ↔ S3-03 contract was unverified.** S3-02 introduced
  `EgressGuardPort` to be satisfied by this story, yet S3-03 had zero ACs about it. *Fix:*
  added **AC-24** — a `mypy --strict` assignability check that `EgressGuard` (the
  all-classmethod class object) is assignable to `EgressGuardPort`; added a Notes
  paragraph on the class-as-port wiring.
- **B5 — Consistency: wrong import in the TDD plan.** `from codegenie.cli import main` —
  `cli.py` exports the click *group* `cli`; `main(argv)` is in `codegenie.__main__`.
  *Fix:* corrected to `from codegenie.__main__ import main`; References block now
  documents the click structure and the `main` location.
- **B6 — Consistency: directory-convention drift (Rule 11).** The story / arch / ADRs
  say `tests/adversarial/`; the codebase uses `tests/adv/` with per-phase subdirs. *Fix:*
  all test paths moved to `tests/adv/phase04/`; added **AC-29** registering a CI-gating
  `phase04_adv` marker (mirroring `phase02_adv`). The arch/ADR `tests/adversarial/`
  prose is flagged for separate doc cleanup — **out of scope** for this story (Rule 3).

### Hardened

- **H1 — `_test_only_loopback_enabled` type was left open** (`ContextVar | threading.local`)
  while AC-15's fixture and the TDD plan already hardcode the `ContextVar` API
  (`.set()` / `.get()`). Committed AC-1 to `ContextVar` and explained why.
- **H2 — AC-8's parenthetical was wrong.** "ContextVar with explicit copy on thread
  boundary" would *defeat* isolation. A fresh `threading.Thread` runs in an empty
  `Context`, so isolation is automatic. Reworded AC-8; the TDD test now joins the worker
  before the fixture resets.
- **H3 — AC-7 was a thin test** (`...` placeholder, "patch create_connection to a
  no-op"). A no-op cannot distinguish correct fall-through from a silently swallowed
  call. Rewrote AC-7 / the TDD test to bind a real ephemeral loopback listener and prove
  a genuine connection, plus a paired negative assertion.
- **H4 — AC-16 adversarial wording was self-defeating.** "Patches `requests`/`urllib3`/
  `httpx` ... `send` ... to attempt connections" — stubbing the high-level transport
  bypasses the socket layer, so the test would assert nothing. Reworded to *drive* the
  real client code paths to `socket.create_connection` and assert `EgressViolation` is
  the raised error / its `__cause__`.
- **H5 — malformed `pinned_to` argument had no AC.** The `ValueError`-at-enter behavior
  lived only in Notes. Added **AC-28** with a parametrized test (`"no-colon"`,
  `"host:notaport"`, `":443"`), keeping `EgressViolation` reserved for well-formed
  not-allowlisted hosts.
- **H6 — `tests/conftest.py` was treated as existing.** It does not. Files-to-touch now
  marks it Create; References explains a new root conftest only *adds* a fixture.
- **H7 — Design-Patterns: functional core was optional.** `_is_admitted(host, port, *,
  loopback_enabled)` lived only in the Refactor section. Elevated to **AC-27** — a pure,
  directly table-tested predicate; the `socket` wrapper is the thin imperative shell.
- **H8 — adversarial tests had no marker.** Added AC-29 / the `phase04_adv` registration
  to `pyproject.toml` files-to-touch.

### Nits

- **N1 — `_WARNING_IDS`** was prescribed unconditionally in Refactor. `egress_guard.py`
  is not a probe and `EgressViolation` is a raised exception, not a warning ID. Reworded:
  add the catalog *only* if the module genuinely emits those `structlog` event IDs, and
  if so wire the import-time `raise AssertionError` validation as probes do.
- **N2 — AC-19 OS-posture check** was underspecified. Clarified: `shutil.which` presence
  check only (reporting configured *rules* needs root and is out of scope); never runs
  `iptables`/`nftables` as a subprocess; reads `_installed` rather than calling
  `install()`.

## Conflict resolutions

- **Arch/ADR `tests/adversarial/` vs codebase `tests/adv/`.** The phase docs are
  pre-implementation prose; the built codebase (2,300 tests, CI markers `adv` /
  `phase02_adv`) is authoritative (Rule 11). Story uses `tests/adv/phase04/`; doc text
  flagged for separate cleanup, not edited here (Rule 3).
- **Story API spelling vs hardened S3-02.** S3-02 is the more recent, validated artifact;
  `pinned_to` is an `AsyncContextManager` and the port contract is byte-fixed. S3-03 now
  conforms.
- **`threading.local()` vs `ContextVar`.** The story offered both; the fixture/tests and
  the `async` adapter path force `ContextVar`. Decided, not hedged. Phase-9 reconsideration
  is an ADR amendment, not a Phase-4 option.

## Edits applied

1. Header `Status: Ready -> HARDENED`; `Depends on` rewritten around the `EgressGuardPort`
   contract; added a `Validation notes` block.
2. References block: documented the click CLI structure, `main` in `__main__`, the
   missing `tests/conftest.py`, the `tests/adv/` convention, the `phase04_adv` marker.
3. AC-1 committed to `ContextVar` and `async` `pinned_to`.
4. AC-7 rewritten around a real ephemeral loopback listener.
5. AC-8 parenthetical corrected (automatic thread isolation).
6. AC-14 wording made precise (`ContextVar`, does not un-install).
7. AC-16/17/18 test paths moved to `tests/adv/phase04/`; AC-16 driver semantics fixed;
   AC-18 import-linter note added.
8. AC-19 clarified (`shutil.which`, no subprocess, reads `_installed`).
9. Added AC-24 (port satisfaction), AC-25 (full-suite green), AC-26 (`sitecustomize`
   autoload subprocess proof), AC-27 (pure `_is_admitted`), AC-28 (malformed `pinned_to`),
   AC-29 (`phase04_adv` marker).
10. Implementation outline updated (decided `ContextVar`, `_ORIGINAL_CREATE_CONNECTION`
    capture, `_is_admitted`, `tests/adv/phase04/`, run-full-suite step).
11. TDD plan rewritten: correct import, `async` `pinned_to` tests, real loopback
    listener, malformed-arg test, subprocess autoload test.
12. Refactor section: `_is_admitted` is now green-path; `_WARNING_IDS` conditioned.
13. Files-to-touch: Create/Modify column; `tests/adv/phase04/` paths; `pyproject.toml`
    added; `tests/conftest.py` marked Create.
14. Out-of-scope: added `bootstrap_runtime()` follow-up and wheel-install caveat.
15. Notes for the implementer: rewrote the `sitecustomize` reliability paragraph
    (honest, verify-don't-assume), added the `EgressGuardPort`-wiring paragraph,
    rewrote the `ContextVar` rationale.

## Design-patterns assessment

The shape is appropriate and was kept, not over-engineered:

- **Adapter at a trust boundary + Dependency Inversion** — `EgressGuard` satisfying
  S3-02's `EgressGuardPort` Protocol is the correct seam; AC-24 now locks it.
- **Functional core / imperative shell** — `_is_admitted` (pure) vs the `socket` wrapper
  (shell); promoted from optional refactor to AC-27.
- **Extension by addition** — the `_BASE_ALLOWLIST` `Final` frozenset is the seam;
  Phase 7's `cgr.dev` is one added row under an ADR amendment. No registry was added —
  one host today, so a registry would breach Rule 2 ("three similar lines beats a
  premature abstraction"). Correctly left as data.
- **Test Capability pattern** — the pytest-fixture-minted `ContextVar` opt-in (ADR-0006)
  is preserved; no boolean-flag anti-pattern reintroduced.

## Verdict rationale

HARDENED. The story's intent, scope, and pattern choices are correct and need no
rewrite. But B1/B2 left the story's defining mechanism unverified and its blast radius
unbounded, B3/B5 would have produced executor-time failures, B4 would have silently
broken the S3-02 integration, and B6 violated Rule 11. Each had a clean in-place fix
that preserves the goal. The story is now executor-ready.

## Recommended next step

`phase-story-executor` can implement S3-03 after S3-02 has landed (it provides the
`anthropic` dependency, `src/codegenie/fallback/leaf/`, and the `EgressGuardPort`
Protocol). Start with the pure `_is_admitted` helper and its table tests, then the
wrapper + `install()`, then `sitecustomize.py` + the AC-26 subprocess proof — if AC-26
fails, resolve the bootstrap mechanism before proceeding. Run `make test` (AC-25) before
declaring GREEN.
