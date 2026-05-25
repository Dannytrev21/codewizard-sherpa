# Story S3-06 — CODEOWNERS + `docs/operations/cassettes.md` runbook + `make refresh-cassettes` ergonomic

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Done — GREEN 2026-05-25 (phase-story-executor; see [`_attempts/S3-06.md`](_attempts/S3-06.md) for the per-AC evidence table + gate log)
**Effort:** S
**Depends on:** S3-05 (`cassettes.lock` + scanner), S3-04 (`CassetteSanitizer` hooks installed in conftest), S3-02 (the live-API recording flow exists)
**ADRs honored:** ADR-0014 (Phase 4 — cassette discipline §Decision item 6 — operator refresh path; §Improvements — CODEOWNERS gate), Gap 2 from `phase-arch-design.md §Gap analysis`

## Validation notes (2026-05-21 — phase-story-validator)

Verdict **HARDENED**. The goal is sound and every AC traces to it, but the draft had real, fixable weaknesses. Changes applied:

1. **`.github/CODEOWNERS` already exists** (Phase 0 + Phase 3 rules, single owner `@Dannytrev21`). The draft asserted it did not exist and instructed `create`. Corrected to **amend**; the initial cassette-steward is `@Dannytrev21` (the repo's established single maintainer = the phase implementer per Gap 2) — no placeholder, no "pause to ask the user" (an autonomous executor cannot pause; the answer is already in the repo).
2. **Gate pass-branch was untestable.** The draft's `make refresh-cassettes` bundled the cheap policy gate with the expensive `pytest --record-mode=all` + live-API action, so no test could prove the gate *passes* with the flag set without spending real tokens. AC-7 now extracts a `_refresh-cassettes-gate` phony prerequisite (policy) from the action — both gate branches are now tokenlessly testable. (Resolves a Test-Quality `block`; the Design-Patterns critic's keep-inline preference is overridden because the extraction is load-bearing for coverage, not speculative — see `_validation/S3-06-…md`.)
3. **Thin / unverifiable ACs hardened.** Removed "or a manual test" / "or skip if no good linter" escape hatches (AC-9, AC-16); the CODEOWNERS test now validates owner-token shape (rejects an unfilled `@<…>` placeholder); the runbook test now asserts all 9 section headings, not 7 prose substrings.
4. **Internal + ADR consistency.** Reconciled the acknowledgement-flag spelling (Context said `--i-understand-this-spends-tokens`; AC-7 uses the make-variable `I_UNDERSTAND_THIS_SPENDS_TOKENS=1`) and added an explicit deviation note — `make` has no flag-passing mechanism. Noted that ADR-0014 §Decision's `cassette-review` token is superseded by Gap 2's single-human `cassette-steward`. Corrected the nightly-drift-job scope: it is **Phase 4** CI scope (ADR-0005 §Consequences), not Phase 6.5.
5. **`docs/contributing.md` exists** — AC-13's conditional resolved to that file. `.PHONY` + POSIX-`/bin/sh` requirement added to AC-7 (the existing `tests/unit/test_makefile_targets.py` contract).

## Context

The first three layers of cassette discipline (sanitize / scanner / manifest) are *automated* controls. The fourth layer is *human*: who is responsible when a cassette needs refreshing? What is the operator's recovery path when CI says "cassette miss — run `make refresh-cassettes`"? Without an explicit answer, the cassette discipline rots — Gap 2 in the gap-analysis section calls this out explicitly: "Six months after Phase 4 ships, an `anthropic` SDK bump silently invalidates ~30 cassettes; nightly drift job catches it but the steward is ambiguous."

This story lands the three load-bearing human-facing artifacts:

1. **`CODEOWNERS`** — names the rotating cassette-steward for `tests/cassettes/anthropic/` and `tests/cassettes/anthropic/cassettes.lock`. GitHub's CODEOWNERS-required-review setting means any cassette diff requires the steward's approval — "I just regenerated and pushed" PRs cannot land without explicit review.
2. **`docs/operations/cassettes.md`** — the runbook. Refresh triggers (nightly drift flag / SDK bump / prompt template change), each with a named owner step. The runbook is also the authoritative documentation of the cassette format (`cassettes.lock` line shape, sanitizer behaviour).
3. **`make refresh-cassettes`** — the operator ergonomic. Wraps `pytest --record-mode=all` with `CODEGENIE_LIVE_LLM=1` and an explicit acknowledgement, rendered as the make-variable `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` (ADR-0014 §Decision item 6 writes this as a CLI flag `--i-understand-this-spends-tokens`; `make` targets cannot accept `--flags`, so the same operator-acknowledgement contract is rendered as a make variable — see AC-7's deviation note). Refuses to run without the acknowledgement, prints a clear "this will spend real Anthropic API tokens" warning, runs `python -m codegenie cassette rebuild-lockfile` afterward, and reminds the operator to commit both the cassettes and the lock together.

Per `phase-arch-design.md §Gap analysis Improvement for Gap 2`: "the CODEOWNERS entry + `docs/operations/cassettes.md` runbook lands *in Step 3*, not deferred — the cost of writing it is one hour."

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis — Gap 2` (cassette rot under SDK upgrade) and the improvement spec.
  - `../phase-arch-design.md §Component 12 — CassetteSanitizer` — "operator refresh path".
- **Phase ADRs:**
  - `../ADRs/0014-cassette-discipline-security-control.md` §Decision items 3 (CODEOWNERS gate) + 5 (nightly drift) + 6 (operator refresh path); §Consequences (`make refresh-cassettes` ergonomic).
  - `../ADRs/0005-no-spki-pin-egress-defense-in-depth.md` §Decision item 3 (nightly drift job — documented here; CI workflow file is Phase 6.5).
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `Makefile` — current targets (`bootstrap`, `check`, `lint`, `test`, `fence`, `clean`); mirror the convention. The recipe shell is POSIX `/bin/sh`; `tests/unit/test_makefile_targets.py` bans bash-isms (`[[ ]]`, `function NAME()`) and asserts every target is declared `.PHONY`.
  - `docs/` directory structure — `docs/production/` and `docs/phases/` exist; this story adds `docs/operations/` as a new subdirectory (or extends if it already exists — verify).
  - **`.github/CODEOWNERS` already exists** — it carries Phase 0 + Phase 3 rules, all owned by the single maintainer `@Dannytrev21`. This story **amends** it by appending the three cassette-discipline rules; it does **not** create the file. Read it first (Rule 8). `tests/unit/test_project_artifacts.py` checks a *fixed subset* of frozen paths (additions do not break it) and exposes a reusable `GITHUB_USER_RE` regex + `_parse_codeowners(text)` helper — consume them for the new well-formedness test rather than re-deriving the parse.
  - `pyproject.toml` for the `codegenie` script entry-point (the Makefile target invokes the CLI) and the `[tool.pytest.ini_options].markers` list (where the new marker is registered).
  - `docs/contributing.md` **exists** — AC-13's CONTRIBUTING note lands there.
- **External:**
  - GitHub CODEOWNERS syntax: `https://docs.github.com/en/repositories/managing-your-repositories-settings-and-customizations/customizing-your-repository/about-code-owners`.

## Goal

Make cassette regeneration **explicit, traceable, and reviewable**: every cassette diff carries CODEOWNERS approval, every operator who runs `make refresh-cassettes` does so knowingly with budget acknowledgement, and every reader of the codebase finds one canonical runbook explaining the workflow.

## Acceptance criteria

### CODEOWNERS

- [ ] AC-1 — The **existing** `.github/CODEOWNERS` is **amended** (not created) by appending exactly these three cassette-discipline rules, using the same `<path> @owner` shape and trailing-slash convention as the rules already in the file:
  ```
  # Cassette discipline (ADR-0014 of Phase 4; single rotating cassette-steward).
  tests/cassettes/anthropic/                @Dannytrev21
  tests/cassettes/anthropic/cassettes.lock  @Dannytrev21
  docs/operations/cassettes.md              @Dannytrev21
  ```
  The initial cassette-steward is **`@Dannytrev21`** — the repo's established single maintainer, which *is* the phase implementer named in `phase-arch-design.md §Gap analysis Improvement for Gap 2`. Match the existing file's path style (the current file uses paths *without* a leading `/`; mirror that — do not introduce a divergent leading-slash style). The directory rule keeps its trailing slash; the two file rules must not (the file's own header comment documents why: GitHub's parser distinguishes files from directories on that bit). The committed file MUST NOT contain a literal `@<…>` placeholder — if the steward handle were genuinely unknown the story would be `BLOCKED`, not shipped with an invalid token; here the handle is known.
- [ ] AC-2 — A comment in the CODEOWNERS file (above the three new rules) explains the rotation cadence ("Steward rotates quarterly; the current steward updates these `@handle` lines as part of handoff. Renewal mechanism: Phase 13.5 operator portal.").
- [ ] AC-3 — The three new rules name a **single human** (`@Dannytrev21`), not a GitHub team/group — single-human ownership is the load-bearing accountability (Gap 2 names it a "rotating cassette-steward"; rotation is human, not team-distributed). **Deviation note:** ADR-0014 §Decision and §Consequences and `phase-arch-design.md §Component 12` write the gate's owner as the team-shaped token `cassette-review`. The Gap 2 improvement (`phase-arch-design.md` lines 1100–1104) is the more specific, later refinement and supersedes it with a single-human `cassette-steward`; this story implements Gap 2. Surface the `cassette-review` token in ADR-0014 §Decision as a documentation cleanup (it should read `cassette-steward`) — do not silently leave the two specs divergent.
- [ ] AC-4 — Repository's branch-protection rule includes "Require review from Code Owners" — this story documents the requirement in `docs/operations/cassettes.md` but the actual GitHub settings change is operator-administered; the story does not depend on having admin access to flip the setting.

### `docs/operations/cassettes.md` runbook

- [ ] AC-5 — `docs/operations/cassettes.md` exists with these sections (verbatim section headings or close):
  1. **What cassettes are and why we care** — one paragraph linking ADR-0014.
  2. **The four discipline layers** — sanitize / scanner / manifest / human (with links to S3-04, S3-05, S3-06).
  3. **Refresh triggers** — three named triggers, each with the owner step:
     - (a) Nightly drift job flags a cassette → cassette-steward investigates within 7 days.
     - (b) Anthropic SDK upgrade → contributor proposing the upgrade also re-records affected cassettes in the same PR.
     - (c) Prompt template change in `plugins/.../skills/` → the PR author re-records affected cassettes.
  4. **How to record a new cassette** — `make refresh-cassettes`; what the flags mean; what to commit.
  5. **`cassettes.lock` format** — a one-line *human-readable illustration* (each line is `<relpath>  <blake3-hex>`) plus a link to the authoritative spec. Do **not** restate the full byte-level contract (sort order, separator width, trailing newline): S3-05's lockfile writer / `codegenie cassette rebuild-lockfile` is the single source of truth, and `phase-arch-design.md §Stable contracts` pins `cassettes.lock`'s line format as a Phase-6.5-consumed stable contract — two normative copies drift. The runbook documents *that* the format exists and *where the spec lives*, not the spec itself.
  6. **Sanitizer behaviour** — what gets stripped (point to S3-04 module docstring as source of truth, not a duplicate spec).
  7. **CODEOWNERS gate** — who approves cassette diffs and how rotation works.
  8. **Nightly drift job** — purpose (TLS / SDK / API shape / prompt-vs-response drift); budget cap; how to interpret PR annotations.
  9. **Troubleshooting** — three scenarios with named recovery paths:
     - "CI says cassette miss" → run `make refresh-cassettes`.
     - "CI says lock drift" → run `python -m codegenie cassette rebuild-lockfile` and commit.
     - "CI says sanitizer violation" → the sanitizer hooks in `conftest.py` should have prevented this; investigate why the hook didn't fire (check `vcr_config` fixture).
- [ ] AC-6 — Every named owner in the runbook is named via **role** (e.g., "cassette-steward", "PR author") not a specific human — humans rotate; the role is stable.

### `make refresh-cassettes` Makefile target

- [ ] AC-7 — `Makefile` gains **two** new targets — a cheap policy gate split from the expensive action so the gate is independently and tokenlessly testable (see TQ-1 in the validation report). Both are declared `.PHONY` (`tests/unit/test_makefile_targets.py` asserts every target is `.PHONY`). The recipe shell is POSIX `/bin/sh` — no bash-isms:
  ```makefile
  # ADR-0014 §Consequences — operator refresh path. The gate is split from the
  # action: `_refresh-cassettes-gate` is a cheap, side-effect-free policy check
  # (testable without spending tokens); `refresh-cassettes` depends on it and
  # carries the expensive recording. ADR-0014 §Decision item 6 writes the
  # acknowledgement as a CLI flag `--i-understand-this-spends-tokens`; `make`
  # targets cannot accept `--flags`, so the same contract is rendered as the
  # make variable I_UNDERSTAND_THIS_SPENDS_TOKENS=1. The intent — an explicit,
  # command-line-visible acknowledgement — is preserved.
  _refresh-cassettes-gate:
  	@if [ "$(I_UNDERSTAND_THIS_SPENDS_TOKENS)" != "1" ]; then \
  		echo "ERROR: refresh-cassettes spends real Anthropic API tokens."; \
  		echo "Re-run with: make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1"; \
  		exit 2; \
  	fi
  	@echo "ack-ok"

  refresh-cassettes: _refresh-cassettes-gate
  	@echo "Recording cassettes against live Anthropic API…"
  	CODEGENIE_LIVE_LLM=1 .venv/bin/pytest -q --record-mode=all -m "uses_anthropic_cassette"
  	.venv/bin/python -m codegenie cassette rebuild-lockfile
  	@echo ""
  	@echo "Recording complete. Review the cassette diffs and commit alongside cassettes.lock."
  	@echo "Cassette diffs require CODEOWNERS approval; tag the current steward."
  ```
  - `_refresh-cassettes-gate` does **only** the `@if … exit 2` check and an `ack-ok` echo — no `pytest`, no `--record-mode`, no API call. This makes *both* branches (block / pass) testable without spending tokens.
  - `refresh-cassettes` lists `_refresh-cassettes-gate` as its first (and only) prerequisite — make builds the prerequisite first, so a missing acknowledgement halts with exit 2 before the recording recipe runs.
  - The `rebuild-lockfile` line is a **separate recipe line** from the `pytest` line (not `&&`-chained) so the lock rebuild still attempts even if `pytest` fails (AC-11).
  - The `-m "uses_anthropic_cassette"` pytest marker selector means only Anthropic-cassette tests re-record; other cassette providers (future) get their own marker (extension by addition — the selector becomes `-m "uses_anthropic_cassette or uses_<x>_cassette"`, no rename).
  - Both `_refresh-cassettes-gate` and `refresh-cassettes` are added to the `.PHONY` line.
- [ ] AC-8 — A `uses_anthropic_cassette` marker is registered in `pyproject.toml` `[tool.pytest.ini_options].markers` (append one entry to the existing `markers` list, matching its `"<name>: <description>"` shape) so the marker is discoverable and `--strict-markers` / unrecognized-marker warnings don't fire. The two S3-02 test functions that record Anthropic cassettes are decorated `@pytest.mark.uses_anthropic_cassette` — locate S3-02's adapter test file (`tests/.../test_*anthropic*` or `test_*leaf*`) and decorate them. If S3-02's recording tests cannot be located, the story is `BLOCKED` (the `-m "uses_anthropic_cassette"` selector matching zero tests would make `make refresh-cassettes` a silent no-op — Rule 12, fail loud).
- [ ] AC-9 — The acknowledgement gate is verified on **both** branches via `_refresh-cassettes-gate`: `make _refresh-cassettes-gate` (no ack) prints the diagnostic and exits 2; `make _refresh-cassettes-gate I_UNDERSTAND_THIS_SPENDS_TOKENS=1` exits 0, prints `ack-ok`, and performs **no** expensive action (its output contains no `pytest`, no `record-mode`, no API call). Both branches are covered by automated tests in `tests/integration/test_makefile_refresh_cassettes_safety.py` — no "manual test" escape hatch.
- [ ] AC-10 — `make refresh-cassettes` invokes `pytest` with `--record-mode=all`, which the `vcr_config` fixture (S3-04 AC-12) honours by *flipping* the record mode from `none` to `all`. The sanitizer hooks fire **during** recording — the cassette bytes on disk are already sanitized.
- [ ] AC-11 — After `pytest` finishes (success or failure), the Makefile runs `python -m codegenie cassette rebuild-lockfile` so the lock is updated alongside cassettes. If `pytest` failed, the lock-rebuild still attempts; if `cassettes.lock` ends up inconsistent (e.g., partial recording), the next `make check` will catch it via S3-05's walker.
- [ ] AC-20 — A static test reads the `refresh-cassettes` recipe body from the `Makefile` and asserts it actually performs the work the story promises — a mutant recipe that drops a line ships green otherwise. The test asserts the recipe body contains `--record-mode=all`, the `-m` selector for `uses_anthropic_cassette`, and `codegenie cassette rebuild-lockfile`; and that `refresh-cassettes` declares `_refresh-cassettes-gate` as a prerequisite (so removing the gate, or slipping an expensive line above it, is caught).
- [ ] AC-21 — The `uses_anthropic_cassette` marker is not just registered but *attached*: `pytest -m uses_anthropic_cassette --collect-only` collects ≥ 1 test item (a test asserts this). This guards the silent-no-op failure mode where `make refresh-cassettes` records nothing because no test carries the marker.

### Documentation cross-linking

- [ ] AC-12 — `CLAUDE.md` (repo root) gains one paragraph under `## Common commands` or `## Conventions` pointing to `docs/operations/cassettes.md` as the source-of-truth for cassette workflow. Surgical edit per Rule 3 — do not refactor the rest of the file.
- [ ] AC-13 — `docs/contributing.md` (which **exists**) gains a surgical note: "Do not run `pytest --record-mode=all` directly. Always use `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`. Direct invocation bypasses the explicit-acknowledgement gate." Rule 3 — append the note, do not refactor the file.

### Verification

- [ ] AC-14 — `tests/integration/test_makefile_refresh_cassettes_safety.py` carries the full safety + shape suite, each test running `subprocess.run(..., env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True)` with a minimal env so no contributor-local `I_UNDERSTAND_THIS_SPENDS_TOKENS` export can bypass a gate test:
  - **Gate blocks:** `make refresh-cassettes` (no ack) → returncode `2`, output contains `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` and `ERROR`.
  - **Gate passes (tokenless):** `make _refresh-cassettes-gate I_UNDERSTAND_THIS_SPENDS_TOKENS=1` → returncode `0`, output contains `ack-ok` and contains **no** `pytest` / `record-mode` substring (proves the gate target performs no expensive action — distinguishes a working gate from one that always blocks).
  - **Prerequisite wired:** the `refresh-cassettes` target lists `_refresh-cassettes-gate` as a prerequisite (static `Makefile` read).
  - **Recipe does the work:** AC-20's static assertions on the `refresh-cassettes` recipe body.
  - **CODEOWNERS well-formed:** AC-16's checks (owner-token shape, no `<`/`>`, three cassette paths present).
  - **Runbook complete:** all 9 AC-5 section headings present (heading-shaped lines, not prose substrings).
  - **Marker registered + attached:** AC-8 + AC-21.
  - No SDK call and no network is needed for any test — every gate test halts before `pytest` starts.
- [ ] AC-15 — `docs/operations/cassettes.md` is built into the mkdocs site. `make docs` passes — note `make docs` already runs `mkdocs build --strict` (do not pass `--strict` to `make` itself; that is a make-flag error). Add the new file to `mkdocs.yml`'s `nav:` (or confirm auto-discovery picks it up — verify by inspecting the built `site/`). Because `mkdocs build --strict` fails on any unresolved internal link, this AC also covers the runbook's cross-links to ADR-0014 / S3-04 / S3-05 — they must be mkdocs-resolvable relative paths.
- [ ] AC-16 — A test in `tests/integration/test_makefile_refresh_cassettes_safety.py` validates `.github/CODEOWNERS` is well-formed (no external linter dependency — GitHub's parser is strict, so a malformed owner token silently disables a rule): every non-comment, non-blank line has ≥ 2 whitespace-separated fields; every owner token matches the GitHub handle/team shape (reuse `GITHUB_USER_RE` from `tests/unit/test_project_artifacts.py`, or `^@[A-Za-z0-9][A-Za-z0-9-]*(/[A-Za-z0-9._-]+)?$`); and the file contains **no `<` or `>` character** — this last check fails loudly if an unfilled `@<…>` placeholder ever ships (enforces AC-1's "no placeholder" requirement, which was previously prose-only).

### Cross-cutting

- [ ] AC-17 — `mypy --strict` clean on any touched Python (this story is mostly docs + Makefile + CODEOWNERS, so the surface is small).
- [ ] AC-18 — `ruff check`, `ruff format --check`, `pre-commit run --all-files` clean.
- [ ] AC-19 — TDD red test exists (AC-14 is the canonical test); was demonstrably failing before implementation; now green.

## Implementation outline

1. Write the failing tests in `tests/integration/test_makefile_refresh_cassettes_safety.py` first (Red — see the TDD plan). Confirm they fail for the right reasons (CODEOWNERS rules absent, runbook absent, gate target absent).
2. **Amend** the existing `.github/CODEOWNERS` — append the three cassette-discipline rules owned by `@Dannytrev21`, matching the file's existing path style and trailing-slash convention (AC-1, AC-2, AC-3). Do not create a new file; do not leave a placeholder.
3. Create `docs/operations/cassettes.md` with the nine sections (AC-5). Reference S3-04 / S3-05 as sources of truth for sanitizer behaviour and the `cassettes.lock` byte format — illustrate, do not restate.
4. Add `mkdocs.yml` entry for the new doc; verify with `make docs` (which runs `mkdocs build --strict`).
5. Add the `_refresh-cassettes-gate` and `refresh-cassettes` targets to `Makefile`; add both to the `.PHONY` line (AC-7).
6. Register the `uses_anthropic_cassette` marker in `pyproject.toml`'s `markers` list, and decorate S3-02's two cassette-recording test functions with `@pytest.mark.uses_anthropic_cassette` (AC-8). Locate S3-02's adapter test file first.
7. Surgical note in `docs/contributing.md` (AC-13) and `CLAUDE.md` (AC-12).
8. Green: confirm every test in the safety suite passes. Verify the gate by hand both ways (`make _refresh-cassettes-gate` → exit 2; `… I_UNDERSTAND_THIS_SPENDS_TOKENS=1` → exit 0). Do **not** run the full `refresh-cassettes` recipe in CI — it spends real tokens and is operator-only.

## TDD plan — red / green / refactor

### Red — write the failing tests first

All tests live in `tests/integration/test_makefile_refresh_cassettes_safety.py`. Each gate test passes a minimal `env={"PATH": "/usr/bin:/bin"}` so no inherited `I_UNDERSTAND_THIS_SPENDS_TOKENS` export can bypass it. Mutation intent is called out per test — a test that does not pin down a *specific wrong implementation* is not pulling its weight (Rule 9).

```python
# tests/integration/test_makefile_refresh_cassettes_safety.py
import re
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIN_ENV = {"PATH": "/usr/bin:/bin"}  # strips any contributor-local ack export
# GitHub handle or org/team; reuse tests/unit/test_project_artifacts.py::GITHUB_USER_RE
OWNER_RE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9-]*(/[A-Za-z0-9._-]+)?$")


def _recipe_body(target: str, makefile: str) -> str:
    """Lines of a target's recipe (tab-indented), excluding the target line."""
    lines, body, in_target = makefile.splitlines(), [], False
    for ln in lines:
        if ln.startswith(f"{target}:"):
            in_target = True
            continue
        if in_target:
            if ln.startswith("\t"):
                body.append(ln)
            elif ln.strip() == "":
                continue
            else:
                break
    return "\n".join(body)


# --- gate: blocks without acknowledgement -----------------------------------
def test_refresh_cassettes_blocks_without_acknowledgement():
    """Mutation guard: an inverted/removed gate would let the recipe run -> not 2."""
    result = subprocess.run(
        ["make", "refresh-cassettes"], cwd=REPO_ROOT, env=MIN_ENV,
        capture_output=True, text=True,
    )
    assert result.returncode == 2, f"expected 2, got {result.returncode}; {result.stderr}"
    combined = result.stdout + result.stderr
    assert "I_UNDERSTAND_THIS_SPENDS_TOKENS=1" in combined
    assert "ERROR" in combined


# --- gate: passes WITH acknowledgement, tokenlessly -------------------------
def test_refresh_gate_passes_with_acknowledgement_and_does_nothing_expensive():
    """Mutation guard: an `exit 2`-always gate makes refresh impossible and ships
    green against the block-test alone. The gate target must pass AND must NOT
    invoke pytest/record-mode (it is policy only — no token spend)."""
    result = subprocess.run(
        ["make", "_refresh-cassettes-gate", "I_UNDERSTAND_THIS_SPENDS_TOKENS=1"],
        cwd=REPO_ROOT, env=MIN_ENV, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"gate must pass with ack; {result.stderr}"
    combined = result.stdout + result.stderr
    assert "ack-ok" in combined
    assert "pytest" not in combined and "record-mode" not in combined, (
        "the gate target must do ONLY the ack check — nothing expensive"
    )


def test_refresh_gate_blocks_without_acknowledgement():
    result = subprocess.run(
        ["make", "_refresh-cassettes-gate"], cwd=REPO_ROOT, env=MIN_ENV,
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "I_UNDERSTAND_THIS_SPENDS_TOKENS=1" in result.stdout + result.stderr


# --- recipe wiring: gate is a prerequisite, recipe does the work ------------
def test_refresh_cassettes_depends_on_gate():
    """Mutation guard: gate removal, or an expensive line slipped above it."""
    text = (REPO_ROOT / "Makefile").read_text()
    m = re.search(r"^refresh-cassettes:\s*(.+)$", text, flags=re.MULTILINE)
    assert m and "_refresh-cassettes-gate" in m.group(1).split(), (
        "refresh-cassettes must list _refresh-cassettes-gate as a prerequisite"
    )


def test_refresh_recipe_records_and_rebuilds_lockfile():
    """Mutation guard: a recipe that drops --record-mode=all or the lock rebuild."""
    body = _recipe_body("refresh-cassettes", (REPO_ROOT / "Makefile").read_text())
    assert "--record-mode=all" in body, "recipe must record cassettes (AC-10)"
    assert "uses_anthropic_cassette" in body, "recipe must select the marker (AC-7)"
    assert "codegenie cassette rebuild-lockfile" in body, "must rebuild lock (AC-11)"


# --- CODEOWNERS: well-formed, no placeholder --------------------------------
def test_codeowners_amended_with_well_formed_cassette_rules():
    """Mutation guard: a literal `@<github-handle>` placeholder (invalid GitHub
    syntax) would ship green against a substring-only check."""
    co = REPO_ROOT / ".github" / "CODEOWNERS"
    assert co.exists(), "CODEOWNERS must already exist — this story amends it"
    text = co.read_text()
    assert "<" not in text and ">" not in text, "unfilled placeholder owner token"
    rules = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        assert len(parts) >= 2, f"CODEOWNERS line lacks an owner: {line!r}"
        for owner in parts[1:]:
            assert OWNER_RE.fullmatch(owner), f"bad owner token: {owner!r}"
        rules[parts[0]] = parts[1:]
    for path in (
        "tests/cassettes/anthropic/",
        "tests/cassettes/anthropic/cassettes.lock",
        "docs/operations/cassettes.md",
    ):
        assert path in rules, f"CODEOWNERS missing cassette rule for {path!r}"


# --- runbook: all 9 sections, heading-shaped --------------------------------
def test_cassettes_runbook_has_all_required_section_headings():
    runbook = REPO_ROOT / "docs" / "operations" / "cassettes.md"
    assert runbook.exists()
    headings = {
        ln.lstrip("#").strip().lower()
        for ln in runbook.read_text().splitlines()
        if ln.lstrip().startswith("#")
    }
    for required in [
        "what cassettes are",
        "four discipline layers",
        "refresh triggers",
        "how to record a new cassette",
        "cassettes.lock format",
        "sanitizer behaviour",
        "codeowners gate",
        "nightly drift job",
        "troubleshooting",
    ]:
        assert any(required in h for h in headings), f"runbook missing heading: {required}"


# --- marker: registered AND attached ----------------------------------------
def test_uses_anthropic_cassette_marker_registered():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    markers = pyproject["tool"]["pytest"]["ini_options"]["markers"]
    assert any(m.startswith("uses_anthropic_cassette") for m in markers), "AC-8"


def test_uses_anthropic_cassette_marker_is_attached_to_a_test():
    """Guards the silent no-op: refresh records nothing if no test carries the
    marker. pytest exits 5 ('no tests collected') when -m matches nothing and 0
    when >= 1 is collected — so returncode is the assertion."""
    result = subprocess.run(
        ["python", "-m", "pytest", "-m", "uses_anthropic_cassette",
         "--collect-only", "-q", "--no-cov"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "no test carries @pytest.mark.uses_anthropic_cassette — `make refresh-cassettes` "
        f"would be a silent no-op (AC-21); collect output:\n{result.stdout}"
    )
```

> The marker-attachment test depends on S3-02's recording tests existing; if S3-02's
> test file genuinely cannot be located the story is `BLOCKED` per AC-8 — do not weaken
> the test to paper over a missing dependency.

### Green — make it pass

Author the three artifacts: CODEOWNERS, runbook, Makefile target. Register the pytest marker.

### Refactor — clean up

- Verify all cross-links resolve (`docs/operations/cassettes.md` → ADR-0014; CLAUDE.md → runbook).
- Run `make docs` and confirm the new doc appears in the site nav.
- Run the safety test in a clean shell to confirm no inherited env-var bypasses the gate.

## Files to touch

| Path | Create / Modify | Why |
|---|---|---|
| `.github/CODEOWNERS` | **Modify** | Append the three cassette-discipline rules owned by `@Dannytrev21` (the file already exists). |
| `docs/operations/cassettes.md` | Create | The runbook (this story's primary documentation artifact). |
| `Makefile` | Modify | `_refresh-cassettes-gate` + `refresh-cassettes` targets; add both to `.PHONY`. |
| `pyproject.toml` | Modify | Register `uses_anthropic_cassette` in the `[tool.pytest.ini_options].markers` list. |
| `tests/.../test_*anthropic*` (S3-02's adapter test file) | Modify | Decorate S3-02's two cassette-recording test functions with `@pytest.mark.uses_anthropic_cassette` so `make refresh-cassettes`'s `-m` selector picks them up (AC-8). Locate the actual path; if absent → `BLOCKED`. |
| `mkdocs.yml` | Modify | Add `docs/operations/cassettes.md` to the nav (if the project doesn't auto-discover). |
| `CLAUDE.md` | Modify | Surgical paragraph pointing to the runbook (Rule 3 — touch only what you must). |
| `docs/contributing.md` | Modify | Surgical note: never run `pytest --record-mode=all` directly; use `make refresh-cassettes` (AC-13). |
| `tests/integration/test_makefile_refresh_cassettes_safety.py` | Create | The safety + shape suite — gate both branches, recipe body, CODEOWNERS well-formedness, runbook headings, marker registered + attached. |

## Out of scope

- Nightly drift job CI workflow file (`.github/workflows/cassette-drift-nightly.yml`) — out of scope **for S3-06 specifically** (this story ships the runbook + CODEOWNERS + Makefile ergonomic, not CI YAML). It is **not** deferred to Phase 6.5: ADR-0005 §Consequences is explicit that "the nightly drift job is in scope for Phase 4's CI surface", and ADR-0014 §Decision item 5 / §Consequences treat it as a Phase-4 deliverable. The workflow file lands via a separate Phase-4 CI-wiring story; S3-06 documents the job's *purpose* in the runbook (AC-5 §8). (What Phase 6.5 owns is the bench harness *reading* `cassettes.lock` per case — see the next bullet — not the drift workflow.)
- The bench harness reading `cassettes.lock` per case — Phase 6.5.
- Multi-vendor cassette directories (`tests/cassettes/<vendor>/`) — Phase 4 ships one vendor (Anthropic); the pattern generalises but is not exercised.
- Operator portal for steward rotation — Phase 13.5.

## Notes for the implementer

- **The CODEOWNERS steward handle is `@Dannytrev21`** — the repo's established single maintainer, which is the phase implementer named by Gap 2. The existing `.github/CODEOWNERS` already owns every gated path with this handle; the three new cassette rules use the same handle. No need to ask the user, and no placeholder — the answer is already in the repo (Rule 8 — read before you write).
- The `make refresh-cassettes` acknowledgement is the make variable `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` — `make` targets cannot accept `--flags`, which is the only reason it is not the `--i-understand-this-spends-tokens` CLI flag that ADR-0014 §Decision item 6 writes. **Be honest about what this gate is and is not:** `make` imports environment variables and command-line variables into `$(VAR)` *identically* — `I_UNDERSTAND_THIS_SPENDS_TOKENS=1 make refresh-cassettes` satisfies the gate just as the command-line form does. The gate is therefore *intentional friction / an explicit acknowledgement*, **not** an isolation boundary or a security control. The command-line form is preferred for readability in shell history, not because env vars are "blocked". Do not claim the gate prevents an env-var bypass — it does not, and the safety test relies only on stripping inherited env, not on the gate distinguishing origins.
- The cassette-refresh PR cycle is intentionally friction-laden:
  1. Operator runs `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1` locally (this is the *only* sanctioned `--record-mode=all` invocation).
  2. Sanitizer hooks fire during recording; cassette bytes on disk are clean.
  3. `python -m codegenie cassette rebuild-lockfile` runs automatically; `cassettes.lock` updated.
  4. Operator commits both cassettes + lock.
  5. CI's `tests/security/test_cassettes_clean.py` walker (S3-05) confirms cleanliness + lock-match.
  6. CODEOWNERS-required-review forces the steward to approve.
  This is *deliberately* slow per ADR-0014 §Tradeoffs ("slower than `pytest --record-mode=all`"); the alternative is a leak risk.
- The `mkdocs.yml` nav may or may not auto-discover; check by running `make docs` (it already runs `mkdocs build --strict`) after adding the file. If it doesn't appear, add an explicit `nav:` entry. Do not pass `--strict` to `make` itself.
- **Why the gate is a separate `_refresh-cassettes-gate` target:** the cheap policy check is split from the expensive action so the *pass* branch is testable without spending real tokens — running the whole `refresh-cassettes` recipe with the acknowledgement set would fire `pytest --record-mode=all` against the live API. This is functional-core/imperative-shell applied at the Makefile level: the gate is pure policy; the recording is the side effect. It is *not* speculative abstraction — it is load-bearing for test coverage of a branch that is otherwise unreachable. If a second token-spending target is ever added, generalise the `@if` block into a shared `_token-spend-gate:` prerequisite *then* (rule of three), not before.
- For the safety test (AC-14): `subprocess.run` with a minimal `env={"PATH": …}` ensures no contributor-local `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` shell export accidentally lets the test "pass" by skipping the gate. Test the gate by *its absence*.
- The runbook should explicitly say "The steward is one human, not a team. Rotation happens quarterly via this file's CODEOWNERS handle. There is no on-call alias substitute." — accountability lives in a name, not a rotation pager.
- After this story lands, S3-02's AC-19 (the two recorded cassettes) becomes *executable* — the operator runs `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`, the two cassettes land sanitized, the lock is generated, both are committed. Coordinate the order: S3-04 → S3-05 → S3-06 → S3-02's AC-19. The first three are infrastructure; the fourth is the actual recording.
