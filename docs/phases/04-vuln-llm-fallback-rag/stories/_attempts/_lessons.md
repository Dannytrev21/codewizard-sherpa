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
