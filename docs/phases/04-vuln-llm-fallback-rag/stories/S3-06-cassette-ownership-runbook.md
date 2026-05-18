# Story S3-06 — CODEOWNERS + `docs/operations/cassettes.md` runbook + `make refresh-cassettes` ergonomic

**Step:** Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline
**Status:** Ready
**Effort:** S
**Depends on:** S3-05 (`cassettes.lock` + scanner), S3-04 (`CassetteSanitizer` hooks installed in conftest), S3-02 (the live-API recording flow exists)
**ADRs honored:** ADR-0014 (Phase 4 — cassette discipline §Decision item 6 — operator refresh path; §Improvements — CODEOWNERS gate), Gap 2 from `phase-arch-design.md §Gap analysis`

## Context

The first three layers of cassette discipline (sanitize / scanner / manifest) are *automated* controls. The fourth layer is *human*: who is responsible when a cassette needs refreshing? What is the operator's recovery path when CI says "cassette miss — run `make refresh-cassettes`"? Without an explicit answer, the cassette discipline rots — Gap 2 in the gap-analysis section calls this out explicitly: "Six months after Phase 4 ships, an `anthropic` SDK bump silently invalidates ~30 cassettes; nightly drift job catches it but the steward is ambiguous."

This story lands the three load-bearing human-facing artifacts:

1. **`CODEOWNERS`** — names the rotating cassette-steward for `tests/cassettes/anthropic/` and `tests/cassettes/anthropic/cassettes.lock`. GitHub's CODEOWNERS-required-review setting means any cassette diff requires the steward's approval — "I just regenerated and pushed" PRs cannot land without explicit review.
2. **`docs/operations/cassettes.md`** — the runbook. Refresh triggers (nightly drift flag / SDK bump / prompt template change), each with a named owner step. The runbook is also the authoritative documentation of the cassette format (`cassettes.lock` line shape, sanitizer behaviour).
3. **`make refresh-cassettes`** — the operator ergonomic. Wraps `pytest --record-mode=all` with the `CODEGENIE_LIVE_LLM=1` env gate and an explicit `--i-understand-this-spends-tokens` flag. Refuses to run without both, prints a clear "this will spend real Anthropic API tokens" warning, runs `python -m codegenie cassette rebuild-lockfile` afterward, and reminds the operator to commit both the cassettes and the lock together.

Per `phase-arch-design.md §Gap analysis Improvement for Gap 2`: "the CODEOWNERS entry + `docs/operations/cassettes.md` runbook lands *in Step 3*, not deferred — the cost of writing it is one hour."

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis — Gap 2` (cassette rot under SDK upgrade) and the improvement spec.
  - `../phase-arch-design.md §Component 12 — CassetteSanitizer` — "operator refresh path".
- **Phase ADRs:**
  - `../ADRs/0014-cassette-discipline-security-control.md` §Decision items 3 (CODEOWNERS gate) + 5 (nightly drift) + 6 (operator refresh path); §Consequences (`make refresh-cassettes` ergonomic).
  - `../ADRs/0005-no-spki-pin-egress-defense-in-depth.md` §Decision item 3 (nightly drift job — documented here; CI workflow file is Phase 6.5).
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `Makefile` — current targets (`bootstrap`, `check`, `lint`, `test`, `fence`, `clean`); mirror the convention.
  - `docs/` directory structure — `docs/production/` and `docs/phases/` exist; this story adds `docs/operations/` as a new subdirectory (or extends if it already exists — verify).
  - There is no existing `CODEOWNERS` file at repo root or `.github/CODEOWNERS` — this story creates it.
  - `pyproject.toml` for the `codegenie` script entry-point (the Makefile target invokes the CLI).
- **External:**
  - GitHub CODEOWNERS syntax: `https://docs.github.com/en/repositories/managing-your-repositories-settings-and-customizations/customizing-your-repository/about-code-owners`.

## Goal

Make cassette regeneration **explicit, traceable, and reviewable**: every cassette diff carries CODEOWNERS approval, every operator who runs `make refresh-cassettes` does so knowingly with budget acknowledgement, and every reader of the codebase finds one canonical runbook explaining the workflow.

## Acceptance criteria

### CODEOWNERS

- [ ] AC-1 — `.github/CODEOWNERS` (or top-level `CODEOWNERS` — pick GitHub's preferred location; `.github/CODEOWNERS` is the convention) exists with at least these lines:
  ```
  # Cassette discipline (ADR-0014 of Phase 4; rotating steward)
  /tests/cassettes/anthropic/                @<github-handle-of-current-steward>
  /tests/cassettes/anthropic/cassettes.lock  @<github-handle-of-current-steward>
  /docs/operations/cassettes.md              @<github-handle-of-current-steward>
  ```
  `<github-handle-of-current-steward>` is filled in at landing — the implementer asks the user / repo maintainer to name the initial steward (the phase implementer per `phase-arch-design.md §Gap analysis Improvement for Gap 2`; renewed via Phase-13.5 operator portal). **Do not invent a handle.**
- [ ] AC-2 — A note in the CODEOWNERS file explains the rotation cadence ("Steward rotates quarterly; current steward updates this file's `@handle` lines as part of handoff. Renewal mechanism: Phase 13.5 operator portal.").
- [ ] AC-3 — The CODEOWNERS file does NOT name a non-human team unless the repo already has the team configured in GitHub — single-human ownership is the load-bearing accountability (the gap analysis names it "rotating cassette-steward"; rotation is human, not team-distributed).
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
  5. **`cassettes.lock` format** — `<relpath>  <blake3-hex>`, sorted, two-space separator, trailing newline. Phase 6.5 reads this format byte-for-byte.
  6. **Sanitizer behaviour** — what gets stripped (point to S3-04 module docstring as source of truth, not a duplicate spec).
  7. **CODEOWNERS gate** — who approves cassette diffs and how rotation works.
  8. **Nightly drift job** — purpose (TLS / SDK / API shape / prompt-vs-response drift); budget cap; how to interpret PR annotations.
  9. **Troubleshooting** — three scenarios with named recovery paths:
     - "CI says cassette miss" → run `make refresh-cassettes`.
     - "CI says lock drift" → run `python -m codegenie cassette rebuild-lockfile` and commit.
     - "CI says sanitizer violation" → the sanitizer hooks in `conftest.py` should have prevented this; investigate why the hook didn't fire (check `vcr_config` fixture).
- [ ] AC-6 — Every named owner in the runbook is named via **role** (e.g., "cassette-steward", "PR author") not a specific human — humans rotate; the role is stable.

### `make refresh-cassettes` Makefile target

- [ ] AC-7 — `Makefile` gains a new target:
  ```makefile
  # ADR-0014 §Consequences — operator refresh path.
  # Spends real Anthropic API tokens; requires explicit acknowledgement.
  refresh-cassettes:
  	@if [ "$(I_UNDERSTAND_THIS_SPENDS_TOKENS)" != "1" ]; then \
  		echo "ERROR: refresh-cassettes spends real Anthropic API tokens."; \
  		echo "Re-run with: make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1"; \
  		exit 2; \
  	fi
  	@echo "Recording cassettes against live Anthropic API…"
  	CODEGENIE_LIVE_LLM=1 .venv/bin/pytest -q --record-mode=all -m "uses_anthropic_cassette"
  	.venv/bin/python -m codegenie cassette rebuild-lockfile
  	@echo ""
  	@echo "Recording complete. Review the cassette diffs and commit alongside cassettes.lock."
  	@echo "Cassette diffs require CODEOWNERS approval; tag the current steward."
  ```
  - The `@if … exit 2` block enforces the explicit-acknowledgement flag.
  - The `-m "uses_anthropic_cassette"` pytest marker selector means only Anthropic-cassette tests re-record; other cassette providers (future) get their own marker.
- [ ] AC-8 — A `pytest.mark.uses_anthropic_cassette` marker is registered in `pyproject.toml` `[tool.pytest.ini_options].markers` so the marker is discoverable and unrecognized-marker warnings don't fire. Tests that record Anthropic cassettes (S3-02's two cassettes) carry the marker.
- [ ] AC-9 — Running `make refresh-cassettes` (without the env-var ack) prints the error message and exits 2; running `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1` proceeds. Test via `pytest`'s `subprocess.run` shim (or a manual test with the implementer verifying the path).
- [ ] AC-10 — `make refresh-cassettes` invokes `pytest` with `--record-mode=all`, which the `vcr_config` fixture (S3-04 AC-12) honours by *flipping* the record mode from `none` to `all`. The sanitizer hooks fire **during** recording — the cassette bytes on disk are already sanitized.
- [ ] AC-11 — After `pytest` finishes (success or failure), the Makefile runs `python -m codegenie cassette rebuild-lockfile` so the lock is updated alongside cassettes. If `pytest` failed, the lock-rebuild still attempts; if `cassettes.lock` ends up inconsistent (e.g., partial recording), the next `make check` will catch it via S3-05's walker.

### Documentation cross-linking

- [ ] AC-12 — `CLAUDE.md` (repo root) gains one paragraph under `## Common commands` or `## Conventions` pointing to `docs/operations/cassettes.md` as the source-of-truth for cassette workflow. Surgical edit per Rule 3 — do not refactor the rest of the file.
- [ ] AC-13 — The CONTRIBUTING note (`docs/contributing.md` if it exists, otherwise inline in `docs/operations/cassettes.md`) mentions: "Do not run `pytest --record-mode=all` directly. Always use `make refresh-cassettes`. Direct invocation bypasses the explicit-acknowledgement flag."

### Verification

- [ ] AC-14 — `make refresh-cassettes` without `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` exits non-zero and prints the diagnostic. A `tests/integration/test_makefile_refresh_cassettes_safety.py` runs `subprocess.run(["make", "refresh-cassettes"], capture_output=True)` and asserts:
  - Return code is `2`.
  - stderr or stdout contains the literal `"I_UNDERSTAND_THIS_SPENDS_TOKENS=1"`.
  - No SDK call is attempted (the test does not need network — the gate fires before pytest starts).
- [ ] AC-15 — `docs/operations/cassettes.md` is built into the mkdocs site (if `make docs` is the project's docs-build step, add the new file to `mkdocs.yml`'s nav or rely on auto-discovery — verify). `make docs --strict` passes.
- [ ] AC-16 — The CODEOWNERS file's syntax is validated — GitHub's CODEOWNERS parser is strict; a Python or shell pre-commit hook (or a CI step) verifies the file parses. Use the existing `pre-commit` hook `mirrors-codeowners-lint` if available, or skip if no good linter exists and rely on GitHub's own validation on push.

### Cross-cutting

- [ ] AC-17 — `mypy --strict` clean on any touched Python (this story is mostly docs + Makefile + CODEOWNERS, so the surface is small).
- [ ] AC-18 — `ruff check`, `ruff format --check`, `pre-commit run --all-files` clean.
- [ ] AC-19 — TDD red test exists (AC-14 is the canonical test); was demonstrably failing before implementation; now green.

## Implementation outline

1. Create `.github/CODEOWNERS` with the three entries (AC-1). Pause to ask the user / maintainer for the current steward's GitHub handle; do not invent.
2. Create `docs/operations/cassettes.md` with the nine sections (AC-5).
3. Add `mkdocs.yml` entry for the new doc (verify the build).
4. Add `refresh-cassettes` target to `Makefile` (AC-7).
5. Register `uses_anthropic_cassette` marker in `pyproject.toml`.
6. Add `tests/integration/test_makefile_refresh_cassettes_safety.py` (AC-14).
7. Surgical edit to `CLAUDE.md` (AC-12).
8. Verify by running `make refresh-cassettes` without the flag → ack-fail; with the flag → would proceed (skip the actual recording in CI; this is operator-only).

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/integration/test_makefile_refresh_cassettes_safety.py
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_refresh_cassettes_requires_explicit_acknowledgement():
    result = subprocess.run(
        ["make", "refresh-cassettes"],
        cwd=REPO_ROOT,
        env={"PATH": "/usr/bin:/bin"},  # minimal env; no inherited I_UNDERSTAND_…
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, f"expected 2, got {result.returncode}; stderr={result.stderr}"
    combined = result.stdout + result.stderr
    assert "I_UNDERSTAND_THIS_SPENDS_TOKENS=1" in combined
    assert "ERROR" in combined


def test_codeowners_file_present_and_lists_cassette_dir():
    co = REPO_ROOT / ".github" / "CODEOWNERS"
    assert co.exists(), "CODEOWNERS file is missing"
    contents = co.read_text()
    assert "/tests/cassettes/anthropic/" in contents
    assert "/tests/cassettes/anthropic/cassettes.lock" in contents
    assert "/docs/operations/cassettes.md" in contents


def test_cassettes_runbook_has_required_sections():
    runbook = REPO_ROOT / "docs" / "operations" / "cassettes.md"
    assert runbook.exists()
    contents = runbook.read_text()
    for section in [
        "Refresh triggers",
        "How to record a new cassette",
        "cassettes.lock format",
        "Sanitizer behaviour",
        "CODEOWNERS gate",
        "Nightly drift job",
        "Troubleshooting",
    ]:
        assert section in contents, f"runbook missing section: {section}"
```

### Green — make it pass

Author the three artifacts: CODEOWNERS, runbook, Makefile target. Register the pytest marker.

### Refactor — clean up

- Verify all cross-links resolve (`docs/operations/cassettes.md` → ADR-0014; CLAUDE.md → runbook).
- Run `make docs` and confirm the new doc appears in the site nav.
- Run the safety test in a clean shell to confirm no inherited env-var bypasses the gate.

## Files to touch

| Path | Why |
|---|---|
| `.github/CODEOWNERS` | Cassette steward + steward of the runbook (this story's primary ownership artifact). |
| `docs/operations/cassettes.md` | The runbook (this story's primary documentation artifact). |
| `Makefile` | `refresh-cassettes` target with safety gate (this story's primary ergonomic artifact). |
| `pyproject.toml` | Register `uses_anthropic_cassette` pytest marker. |
| `mkdocs.yml` | Add `docs/operations/cassettes.md` to the nav (if the project doesn't auto-discover). |
| `CLAUDE.md` | Surgical paragraph pointing to the runbook (Rule 3 — touch only what you must). |
| `tests/integration/test_makefile_refresh_cassettes_safety.py` | Test the gate fires; CODEOWNERS file shape; runbook section presence. |

## Out of scope

- Nightly drift job CI workflow file (`.github/workflows/cassette-drift-nightly.yml`) — ADR-0014 §Decision item 5 mentions it; the workflow file lands in Phase 6.5 (per `phase-arch-design.md §Resource & cost profile`). This story documents its purpose in the runbook only.
- The bench harness reading `cassettes.lock` per case — Phase 6.5.
- Multi-vendor cassette directories (`tests/cassettes/<vendor>/`) — Phase 4 ships one vendor (Anthropic); the pattern generalises but is not exercised.
- Operator portal for steward rotation — Phase 13.5.

## Notes for the implementer

- **Ask before inventing a CODEOWNERS handle.** The phase implementer is the initial steward per the gap-analysis spec, but the GitHub handle must be a real one. If the user / repo maintainer hasn't named one, surface the question (Rule 1 — no silent assumptions) rather than putting a placeholder.
- The `make refresh-cassettes` gate uses a Makefile variable (`I_UNDERSTAND_THIS_SPENDS_TOKENS=1`) rather than an environment variable so it is *explicitly visible at the command line* — `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1` reads as a contract acknowledgement, not a hidden shell-state side effect. Do not flip to env-var.
- The cassette-refresh PR cycle is intentionally friction-laden:
  1. Operator runs `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1` locally (this is the *only* sanctioned `--record-mode=all` invocation).
  2. Sanitizer hooks fire during recording; cassette bytes on disk are clean.
  3. `python -m codegenie cassette rebuild-lockfile` runs automatically; `cassettes.lock` updated.
  4. Operator commits both cassettes + lock.
  5. CI's `tests/security/test_cassettes_clean.py` walker (S3-05) confirms cleanliness + lock-match.
  6. CODEOWNERS-required-review forces the steward to approve.
  This is *deliberately* slow per ADR-0014 §Tradeoffs ("slower than `pytest --record-mode=all`"); the alternative is a leak risk.
- The `mkdocs.yml` nav may or may not auto-discover; check by running `make docs --strict` after adding the file. If it doesn't appear, add an explicit `nav:` entry.
- For the safety test (AC-14): `subprocess.run` with a minimal `env={"PATH": …}` ensures no contributor-local `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` shell export accidentally lets the test "pass" by skipping the gate. Test the gate by *its absence*.
- The runbook should explicitly say "The steward is one human, not a team. Rotation happens quarterly via this file's CODEOWNERS handle. There is no on-call alias substitute." — accountability lives in a name, not a rotation pager.
- After this story lands, S3-02's AC-19 (the two recorded cassettes) becomes *executable* — the operator runs `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`, the two cassettes land sanitized, the lock is generated, both are committed. Coordinate the order: S3-04 → S3-05 → S3-06 → S3-02's AC-19. The first three are infrastructure; the fourth is the actual recording.
