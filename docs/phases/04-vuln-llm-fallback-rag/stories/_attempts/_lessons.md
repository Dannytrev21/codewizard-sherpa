# Cross-story lessons — Phase 04

Append-only. Add short lessons that reduce risk for later stories.

## L-1 — Shared identifier catalog exact-set tests must move with `__all__` (S1-01)

Adding a new identifier to `src/codegenie/types/identifiers.py` is a three-site
kernel change: the `NewType` declaration, `__all__`, and `_NEWTYPE_REGISTRY`.
The existing `tests/unit/types/test_identifiers_phase3.py` exact-set and
registry tests are intentionally shared across phases; future identifier stories
should extend that roster in the same commit rather than adding a phase-local
duplicate assertion.

## L-2 — Local macOS full-suite timing can fail outside story scope (S1-01)

`tests/adv/test_tsconfig_pathological.py::test_gather_under_pathological_tsconfig_silently_swallows_under_two_seconds`
is a wall-clock test around the full gather CLI. During S1-01 it failed
reproducibly on local macOS at 2.06-2.65s against a 2.0s cap while the focused
story gates were green and latest `master` CI had passed. Treat this as a
separate timing-flake/performance triage item unless CI reproduces it.

## L-3 — Verbatim TDD-plan snippets aren't always runnable — verify `textwrap.dedent` indentation when generating multi-line code under `match` (S1-02)

The TDD-plan snippet for the mypy-exhaustiveness meta-test interpolated
generated `case` arms into a `textwrap.dedent`-wrapped template; the arms
emitted 8 leading spaces and the surrounding template lines also had 8
leading spaces, so `dedent` stripped 8 from everything — including the
arms — collapsing the `case` lines to column 0 *underneath* a `match p:`
sitting at column 4. mypy reported a `[syntax]` error instead of the
intended exhaustiveness diagnostic, and the F4 assertion fired correctly
("mypy failed but not for an exhaustiveness reason"). Fix: emit arms at 16
leading spaces so dedent leaves them at column 8, matching the catch-all
arm. Future stories generating code under indented blocks via `dedent`
should sanity-print the rendered source once before asserting on mypy
output.

## L-5 — Shared utilities used by two leaf packages must live in the kernel (S1-04)

A reusable validator / type alias shared between `codegenie.rag.models` and
`codegenie.fallback.budget` cannot live in either leaf package — the
`fallback/__init__.py` re-export side-effect creates a transient cycle
(`rag.models` → `fallback.plan_proposal` → `fallback/__init__.py` →
`fallback.budget` → `rag.models`) that mypy does NOT catch but pytest
collection breaks on at runtime. The canonical home is
`codegenie.types/<tiny module>.py` — same precedent as `PackageManager`
moving to `codegenie.types.identifiers` (ADR-0013 Amendment 2026-05-20).
The reverse direction (kernel imports leaf) is forbidden by `import-linter`.

## L-4 — Local `lint-imports` console script is not on the system PATH by default (Phase 4)

`tests/unit/test_lint_imports_canary.py` resolves the `lint-imports` binary
via `shutil.which`, which scans `$PATH` only — not the active venv's `bin/`.
On a default macOS shell where the venv isn't sourced, the canary fails with
`AssertionError: lint-imports console script must be on PATH`. CI passes
because the GitHub Actions runner sources the venv. To reproduce CI locally,
run `PATH="$PWD/.venv/bin:$PATH" pytest …` — or `source .venv/bin/activate`.
This is the same root cause as the macOS-runner-vs-CI drift in L-2: treat
PATH-resolution failures as environment hygiene, not regressions.

## L-5 — Two same-named classes in two import spaces is a smell — pick distinct names early (Phase 4)

S2-02 names both the `CanaryResult` sum-variant *and* the event class
`CanaryCollision`. The validator hardened both ACs without flagging the
collision. At Stage-2 implementation time, importing both classes into a
single test module is structurally impossible. The fix is small but
load-bearing: rename the event to `CanaryCollisionEvent`, keep the
on-the-wire discriminator value (`canary_collision`) intact so the story's
AC-12 wire contract still holds. When two layers naturally want the same
name, prefer suffixing the *outer* (event/wrapper) class and leaving the
*inner* (model/variant) class with the bare name — keeps the rename
reversible if the story author wants the bare name on the event later.

## L-6 — A Hypothesis property that depends on an unguessable secret must construct that secret in the strategy (Phase 4)

S2-02 AC-8 says "the close-delimiter never appears in fenced content." A
bare `@given(payload=st.text())` strategy *passes vacuously* against an
implementation that does no in-body delimiter check at all — the 32-hex
nonce is unguessable at 2⁻¹²⁸. The validator caught this. The lesson
generalises: any property of the form "`SECRET not in output`" where
`SECRET` is a per-call random value needs the strategy to draw `SECRET`
itself and embed it in the input — otherwise the strategy is structurally
unable to reach the violation. Same applies to capability tokens,
session IDs, BLAKE3 hashes, anything keyed on a per-call random.

## L-7 — A `# type: ignore[<code>]` on the call site under test silently nullifies the gate (S3-01)

S2-05 shipped `tests/fixtures/typecheck/budget_token_missing.py` with
`# type: ignore[call-arg]` on the very `leaf.invoke(...)` call whose
missing-keyword-argument diagnostic the gate asserts on. While S3-01
hadn't landed, `pytest.importorskip` skipped the test cleanly and
nobody noticed. The moment S3-01 turned the gate live, `mypy --strict`
exited 0 — exactly the regression the gate exists to catch — because
the `[call-arg]` suppression hid it. Lesson: a fixture asserting "mypy
errors with diagnostic X" must NEVER suppress X inline. Suppress the
expected *noise* (placeholder values, unrelated arg-types) but leave
the diagnostic-under-test surfaced. Reviewer heuristic: any
`# type: ignore[<code>]` on the call line a fence test asserts on is a
red flag — the suppression turns the gate into a tautology.

## L-9 — Async httpx bypasses `socket.create_connection` — wrapper is a sync-path defense only (S3-03)

S3-03 AC-18 prose claims `httpx` "ultimately funnels through
`socket.create_connection`". That is only true for **sync** httpx (and
for stdlib `urllib`/`urllib3`). Async httpx delegates to
`asyncio.BaseEventLoop.create_connection` → `loop.sock_connect` on a
raw socket — the `EgressGuard` wrapper does not see it. The Phase-4
adapter's async SDK call inside `AnthropicLeafAdapter` is defended by
the explicit `egress_guard.pinned_to(...)` envelope (the suspenders),
not by the socket wrapper (the belt). Future stories that need to
close the asyncio gap should hook either `asyncio.BaseEventLoop._sock_connect`
or the underlying `socket.socket.connect` (with an IP-allowlist cache
populated by a wrapped `getaddrinfo`). For now, split any "SDK does
not bypass" AC into a sync-client test (genuine wrapper proof) plus a
structural pin of the residual asyncio surface, so a future closure
updates the assertion deliberately rather than letting the gap widen
silently.

## L-10 — `isinstance(x, dict)` fails on third-party `MutableMapping`-only subclasses; use `Mapping` (S3-04)

vcrpy's `HeadersDict` is a `CaseInsensitiveDict` (`MutableMapping`)
subclass but **not** a `dict` subclass. My first-pass
`_normalize_headers` used `isinstance(headers, dict)` and fell through
to the stringify fallback for real `vcr.request.Request` objects —
mangling the whole headers object into one `(repr_string, "")` row.
The unit-shim tests (plain `dict`) passed; only the integration test
against the real type caught the bug. Lesson: when accepting "container
of headers" from a third-party library, type-check against `Mapping`
(or `Iterable[tuple[K, V]]` for the pair-list shape) — `dict` is the
wrong contract because container-type subclassing is library-author's
choice, not the protocol. Same applies to bytes-or-bytearray vs
`bytes`, `Sequence` vs `list`, etc. The integration test that uses the
real third-party type is load-bearing — a dict shim cannot expose this
class of bug.

## L-8 — Reconcile cross-story module-name drafts before the gate flips (S3-01)

S2-05 named the gated-on module `codegenie.fallback.leaf.protocol`;
S3-01 (the contract owner — AC-1 names `port.py`) settled on
`codegenie.fallback.leaf.port`. When the S2-05 gate was written its
target module did not exist yet, so any name "looked correct enough."
When S3-01 GREENed under the canonical name, the `importorskip`
silently kept the test skipped (no error — the path just does not
resolve), defeating the gate's purpose. The S3-01 validator had
already flagged AC-10 for the same class of bug (pointing at a
not-yet-existent sibling test). General rule: "gated-on-next-story"
tests must pin the module path to the *next story's canonical
surface*, not a draft name; the next-story executor's first job is
to re-grep the gating-test for its module path and reconcile it
before declaring GREEN.

## L-11 — The Phase-4 raw-`str` fence treats function-name substrings as domain IDs (S3-05)

`tests/fence/test_phase4_no_raw_str_for_domain_ids.py` walks
`src/codegenie/fallback/` + `src/codegenie/rag/` and flags any
**function** whose name contains a domain keyword (`cassette`,
`cve_id`, `budget_token`, `chain_head`, `nonce`, …) and whose return
annotation is a raw primitive. So `def compute_cassette_digest(...) ->
str` is a fence break — the name carries the domain identity.
Use the existing newtype from
`codegenie.types.identifiers` (here: `BlobDigest`, the
algorithm-agnostic 64-hex digest type the whole repo reuses) rather
than inventing a parallel `CassetteDigest`. The fence applies to
parameter names too — but those usually take `Path`-shaped types, so
breaks land more often on returns.

## L-12 — Local pre-commit hooks backed by a CLI need fence-aware entries (S3-05)

`tests/unit/test_precommit_and_docs_config.py::test_precommit_config_declares_exactly_the_required_hooks`
asserts every `repo: local` hook either points at a real script file
or contains the literal `grep`. A CLI-driven hook
(`python -m codegenie cassette rebuild-lockfile --check`) trips the
fence even though it's plainly not a stub. Per Rule 7 the right fix is
to widen the fence to recognize `python -m <module>` / `python
<script>` rather than wrap the CLI in a shim under `scripts/` — the
shim adds a code path with no semantic value. S3-05 widened the fence;
future CLI-driven hooks need no further change.

---

## L-13 (S3-06) — macOS pre-commit hooks that invoke bare `python` fail locally

S3-05's `cassette-lock-check` hook uses `entry: python -m codegenie cassette
rebuild-lockfile --check`. macOS default Python installs ship `python3` only,
no `python` shim — so `pre-commit run --all-files` fails locally with
"Executable `python` not found". CI Linux runners have `python` available so
the hook passes there (and the S3-05 commit landed green). Three resolution
paths if this ever becomes load-bearing: (a) ship `scripts/<hook>.sh` shim,
(b) widen hook entry to resolve via `sys.executable`-equivalent, (c) document
the divergence in `docs/contributing.md`. Same shape as L-2/L-4 — surfaces
locally, invisible to CI.

## L-14 (S3-06) — fix source data over loosening a literal-spec test

When a story spec writes a literal assertion (e.g. `assert "<" not in text`),
prefer to fix the data the test reads over weakening the test. A test that
strips its own input to pass is no longer a guardrail. S3-06's CODEOWNERS
comment containing `>= 1` violated the AC-16 placeholder-rejection check;
rewording the comment to "at least one" kept the protection intact (Rule 9 —
tests verify intent, not just behavior).

## L-15 (S3-06) — `sys.executable` over bare `"python"` for `subprocess.run`

When a test invokes Python via `subprocess.run`, always use `sys.executable`
unless the test deliberately exercises PATH resolution. Bare `"python"` is
absent on default macOS PATH (`/usr/bin/python3` is the only shipped binary)
and surfaces as `FileNotFoundError` instead of the test's intended diagnostic.
The MIN_ENV pattern (`{"PATH": "/usr/bin:/bin"}`) for gate-isolation testing
strips the venv from PATH — when MIN_ENV is in effect, call `make` (which
finds its own tools); when MIN_ENV is not in effect, use `sys.executable` for
the interpreter.
