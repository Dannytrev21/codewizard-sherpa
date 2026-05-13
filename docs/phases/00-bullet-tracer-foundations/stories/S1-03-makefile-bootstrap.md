# Story S1-03 — Makefile + uv lock + bootstrap targets

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Ready (validated 2026-05-12 — HARDENED)
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0006

## Validation notes

Validated: 2026-05-12
Verdict: HARDENED
Findings addressed: 9 total — 0 blocks, 6 hardens, 3 nits

Changes applied:
- AC-2 strengthened — Test 3 now asserts `python -m pip install` (not the substring `pip install`, which is also contained in `uv pip install` — a single `uv pip install -e ".[dev]"` line would have passed both branch checks, masking a missing fallback). AC-2 wording tightened to require both literal commands and a shell `command -v uv` gate — Test-Quality F2.
- AC-3 reworded — committed to **prerequisite-style** `check: lint typecheck test fence` (the form Make stops at the first failure with). The original wording "runs `make lint && make typecheck && ...`" suggested recipe-chaining; the green example used prerequisites; Test 5's regex only accepted prerequisites. AC and test now agree — Consistency F1.
- AC-4 strengthened — every named target (`lint`, `typecheck`, `test`, `fence`) now has its recipe body verified contains the load-bearing tool invocation, not just that the target is declared. Closes the "lazy `lint:\n\techo lint` passes every test" gap — Coverage F1, Test-Quality F4.
- AC-5 strengthened — `make docs` recipe must contain `mkdocs build --strict` literally (the `--strict` flag is the load-bearing arch §CI-gates clause; `mkdocs build` alone silently downgrades the docs gate) — Coverage F7.
- AC-6 strengthened — `make audit-verify` recipe must contain `python -m codegenie audit verify` literally — Coverage F1.
- AC-7 strengthened — added a lockfile-parity clause: every package named in `[project.dependencies]` and `[project.optional-dependencies.dev]` must appear in `uv.lock`'s `[[package]]` table. Closes the "stale `uv.lock` passes file-existence test" gap — Coverage F3.
- AC-8 relaxed — dropped "was committed" (process clause unverifiable from working tree, same fix applied to S1-01 and S1-02); restated as "exists and is green" — Coverage F4.
- AC-9 added — POSIX-`/bin/sh`-only invariant: no `[[`/`]]`/`function NAME()` in any recipe body. Bridges the implementer-note warning to an executable assertion that catches macOS-vs-Linux divergence regressions — Coverage F5.
- TDD plan rewritten — Tests 3 + 5 strengthened in place; Tests 6, 7, 8, 9 added (per-target recipe-body verification, POSIX-sh structural check, lockfile parity). Total: 9 tests (was 5). Every AC now has at least one mutation-resistant test that would fail under an obviously wrong implementation.

## Context

The reviewer's first contact with the repo is `git clone && make bootstrap && make check`. If `make bootstrap` doesn't install a working dev environment or `make check` doesn't run the four quality gates from S1-02 plus the fence, every later step's friction tax compounds. This story plants the `Makefile` whose targets every subsequent story (and every CI job in S1-05) reuses, and commits a `uv.lock` so installs are reproducible.

The Makefile is the project's *imperative* surface — what humans and CI both invoke. ADR-0006's tradeoff row ("the `Makefile` `bootstrap` target installs `[dev]`") is honored here, and the targets all work with `uv` as the accelerator *or* with plain `pip` as fallback per the synthesis's open question #1 from `phase-arch-design.md §Open questions`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / CI gates` — the six job names that the `Makefile` targets must align with: `lint`, `typecheck`, `test`, `security`, `docs`, `fence`.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — row "Async coordinator from day one" doesn't apply here, but row "`uv` as hard requirement or optional accelerator" is open and this story implements both-paths-work.
  - `../phase-arch-design.md §Open questions deferred to implementation` Q1 — `uv` vs `pip`; the Makefile is where the decision is enforced operationally.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-pyproject-toml-extras-shape.md` — ADR-0006 — `make bootstrap` installs `[dev]`; `fence` job installs base `[project]` (no extras).
- **Source design:**
  - `../High-level-impl.md §Step 1` — Features delivered, "`uv.lock` committed; `Makefile` with `bootstrap`, `check`, `lint`, `typecheck`, `test`, `docs`, `fence`, `audit-verify` targets (all targets work with and without `uv`)."
  - `../High-level-impl.md §Step 1 Done criteria` — "`make bootstrap` installs a working dev environment on a clean macOS or Linux box. `make check` runs lint + typecheck + test + fence locally and exits 0."
- **Existing code:**
  - `pyproject.toml` from S1-01 — the source of `[project.optional-dependencies].dev`.

## Goal

`make bootstrap && make check` from a clean checkout exits 0 on macOS and Linux without requiring `uv` to be preinstalled, and `uv.lock` is committed at the repo root.

## Acceptance criteria

- [ ] **AC-1.** `Makefile` exists at the repo root with targets `bootstrap`, `check`, `lint`, `typecheck`, `test`, `docs`, `fence`, `audit-verify`, and `clean`; each target name appears in a `.PHONY:` declaration.
- [ ] **AC-2.** The `bootstrap` recipe contains **all three** of: a shell `command -v uv` check (or `which uv`), the literal command `uv pip install -e ".[dev]"` in the uv-present branch, and the literal command `python -m pip install -e ".[dev]"` in the fallback branch. Detection is shell-only (no `python -c` / `python -m` invocation used to *detect* uv — `python -m pip install` in the fallback branch is the install, not the detection).
- [ ] **AC-3.** `check` is implemented as a Make prerequisite chain: `check: lint typecheck test fence` — exactly those four prerequisites in that order, with no recipe body. (Make's prerequisite semantics stop at the first failed prerequisite; this matches the goal's "exits 0 from a clean checkout" intent without requiring shell `&&` chaining inside a recipe.)
- [ ] **AC-4.** Each of the four `check` prerequisites has the required tool invocation **literally present** in its recipe body:
  - `lint` recipe contains `ruff check` and `ruff format --check`.
  - `typecheck` recipe contains `mypy --strict src/` (or `mypy --strict src`).
  - `test` recipe contains `pytest -q`.
  - `fence` recipe contains `pytest -q tests/unit/test_pyproject_fence.py` (the fence test file lands in S1-05; this target merely invokes pytest with the path).
- [ ] **AC-5.** The `docs` recipe contains `mkdocs build --strict` literally (the `--strict` flag is load-bearing per `phase-arch-design.md §CI gates` job 5; `mkdocs build` alone silently downgrades the docs gate). The curated `nav` lands in S1-04; this target's only job is to invoke `mkdocs` with `--strict`.
- [ ] **AC-6.** The `audit-verify` recipe contains `python -m codegenie audit verify` literally (the subcommand lands in S4-02; this target's job is to call it).
- [ ] **AC-7.** `uv.lock` exists at the repo root, is non-empty, **and is in lockstep with `pyproject.toml`** — every package named in `[project.dependencies]` and `[project.optional-dependencies.dev]` appears (case-insensitive, normalizing `_`↔`-`) in `uv.lock`'s `[[package]]` table. Closes the "stale lockfile" failure mode where `uv.lock` predates the S1-01 dependency set.
- [ ] **AC-8.** The TDD test file `tests/unit/test_makefile_targets.py` exists, and `pytest -q tests/unit/test_makefile_targets.py` exits 0.
- [ ] **AC-9.** No recipe body in `Makefile` contains bash-only constructs (`[[`, `]]`, or `function NAME()` syntax). Recipes default to `/bin/sh` (POSIX); a bash-ism here is a latent macOS-vs-Linux divergence the goal explicitly forbids ("exits 0 on macOS and Linux"). The implementer note about POSIX-sh-only is now load-bearing on the test surface.

## Implementation outline

1. Write the red test in `tests/unit/test_makefile_targets.py` per the TDD plan.
2. Author the `Makefile` with the nine `.PHONY` targets; use shell `command -v uv >/dev/null 2>&1` for the detection branch in `bootstrap`.
3. Generate `uv.lock` locally by running `uv lock` after S1-01's `pyproject.toml` is in place; commit the file.
4. Run `make bootstrap` from a clean venv on macOS; confirm a working dev install.
5. Run `make check` and observe the chain (some sub-targets may fail until the underlying tests land in later stories; document expected failures in the PR body).
6. Confirm the red test passes against the new `Makefile`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_makefile_targets.py`

```python
# tests/unit/test_makefile_targets.py
import re
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = PROJECT_ROOT / "Makefile"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
UV_LOCK = PROJECT_ROOT / "uv.lock"

REQUIRED_TARGETS = {
    "bootstrap", "check", "lint", "typecheck", "test",
    "docs", "fence", "audit-verify", "clean",
}


def _recipe_body(target: str, text: str) -> str:
    """Return the literal recipe-body text for `target` (the tab-indented lines
    immediately following `target:` up to the next non-tab line). Empty string
    if the target has no recipe (e.g., a prerequisite-only target like `check`)."""
    m = re.search(
        rf"^{re.escape(target)}:[^\n]*\n((?:\t.*\n)*)",
        text,
        flags=re.MULTILINE,
    )
    return m.group(1) if m else ""


# --- AC-1 -------------------------------------------------------------------

def test_makefile_exists_at_repo_root() -> None:
    # AC-1: file present at root
    assert MAKEFILE.is_file(), "Makefile must exist at the repo root"


def test_makefile_declares_all_required_targets_as_phony() -> None:
    # AC-1: nine targets declared, all .PHONY
    text = MAKEFILE.read_text()
    declared = set(re.findall(r"^([a-zA-Z][\w\-]*):", text, flags=re.MULTILINE))
    missing = REQUIRED_TARGETS - declared
    assert not missing, f"Makefile missing targets: {missing}"
    phony_decls = re.findall(r"^\.PHONY:\s*(.+)$", text, flags=re.MULTILINE)
    phony_names = {name for line in phony_decls for name in line.split()}
    assert REQUIRED_TARGETS.issubset(phony_names), \
        f".PHONY missing: {REQUIRED_TARGETS - phony_names}"


# --- AC-2 -------------------------------------------------------------------

def test_bootstrap_recipe_has_both_uv_and_python_m_pip_branches() -> None:
    # AC-2: both branches present; substrings chosen so they DO NOT overlap.
    # NOTE: the bare substring "pip install" overlaps with "uv pip install",
    # so a single uv-only line would falsely satisfy a "pip install" check.
    # We assert "python -m pip install" instead — that string appears ONLY in
    # the fallback branch, never in the uv branch.
    body = _recipe_body("bootstrap", MAKEFILE.read_text())
    assert body, "bootstrap must have a recipe"
    assert "uv pip install" in body, \
        "bootstrap must use `uv pip install` when uv is available"
    assert "python -m pip install" in body, \
        "bootstrap must fall back to `python -m pip install` when uv is absent " \
        "(NOT just `pip install` — that substring is also inside `uv pip install`)"
    assert "command -v uv" in body or "which uv" in body, \
        "bootstrap must detect uv on PATH via shell (`command -v uv` or `which uv`); " \
        "Python-based detection is forbidden by AC-2"


# --- AC-3 -------------------------------------------------------------------

def test_check_is_prerequisite_chain_in_exact_order() -> None:
    # AC-3: prerequisite-style, exact order, no recipe body
    text = MAKEFILE.read_text()
    m = re.search(r"^check:\s*(.+)$", text, flags=re.MULTILINE)
    assert m is not None, "check target must exist"
    deps = m.group(1).split()
    assert deps == ["lint", "typecheck", "test", "fence"], \
        f"`make check` must chain lint → typecheck → test → fence as prerequisites; got {deps}"
    # AC-3: no recipe body — Make's prereq semantics handle stop-on-first-failure
    body = _recipe_body("check", text)
    assert body.strip() == "", \
        f"`check` should be prerequisites-only (no recipe body); got body:\n{body}"


# --- AC-4 -------------------------------------------------------------------

def test_lint_recipe_invokes_ruff_check_and_ruff_format_check() -> None:
    body = _recipe_body("lint", MAKEFILE.read_text())
    assert "ruff check" in body, "lint must invoke `ruff check`"
    assert "ruff format --check" in body, "lint must invoke `ruff format --check`"


def test_typecheck_recipe_invokes_mypy_strict_on_src() -> None:
    body = _recipe_body("typecheck", MAKEFILE.read_text())
    # accept both `mypy --strict src/` and `mypy --strict src`
    assert re.search(r"mypy --strict src/?(\s|$)", body), \
        "typecheck must invoke `mypy --strict src/`"


def test_test_recipe_invokes_pytest_q() -> None:
    body = _recipe_body("test", MAKEFILE.read_text())
    assert "pytest -q" in body, "test must invoke `pytest -q`"


def test_fence_recipe_invokes_pytest_on_fence_test_path() -> None:
    body = _recipe_body("fence", MAKEFILE.read_text())
    assert "pytest -q tests/unit/test_pyproject_fence.py" in body, \
        "fence must invoke `pytest -q tests/unit/test_pyproject_fence.py`"


# --- AC-5, AC-6 -------------------------------------------------------------

def test_docs_recipe_invokes_mkdocs_build_strict() -> None:
    # AC-5: `--strict` is load-bearing per phase-arch §CI gates; bare `mkdocs build`
    # silently downgrades the docs gate.
    body = _recipe_body("docs", MAKEFILE.read_text())
    assert "mkdocs build --strict" in body, \
        "docs must invoke `mkdocs build --strict` (the --strict flag is load-bearing)"


def test_audit_verify_recipe_invokes_codegenie_audit_verify() -> None:
    # AC-6
    body = _recipe_body("audit-verify", MAKEFILE.read_text())
    assert "python -m codegenie audit verify" in body, \
        "audit-verify must invoke `python -m codegenie audit verify`"


# --- AC-7 -------------------------------------------------------------------

def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def _declared_packages_from_pyproject() -> set[str]:
    pyproj = tomllib.loads(PYPROJECT.read_text())
    deps: list[str] = list(pyproj["project"].get("dependencies", []))
    deps += list(
        pyproj["project"].get("optional-dependencies", {}).get("dev", [])
    )
    declared: set[str] = set()
    for spec in deps:
        # Take the leading [A-Za-z0-9._-]+ as the package name.
        m = re.match(r"[A-Za-z0-9._-]+", spec)
        if m:
            declared.add(_normalize(m.group(0)))
    return declared


def test_uv_lock_exists_and_is_non_empty() -> None:
    # AC-7 (existence half)
    assert UV_LOCK.is_file(), "uv.lock must be committed at the repo root"
    assert UV_LOCK.stat().st_size > 0, "uv.lock must not be empty"


def test_uv_lock_is_in_lockstep_with_pyproject_dep_set() -> None:
    # AC-7 (parity half): every package named in pyproject.toml's
    # [project.dependencies] and [project.optional-dependencies.dev] must
    # appear in uv.lock's [[package]] table. Catches stale lockfiles that
    # predate S1-01's pyproject.toml without forcing the test to invoke `uv`.
    declared = _declared_packages_from_pyproject()
    lock = tomllib.loads(UV_LOCK.read_text())
    locked = {_normalize(p["name"]) for p in lock.get("package", [])}
    missing = declared - locked
    assert not missing, (
        f"uv.lock is stale relative to pyproject.toml; missing packages: {sorted(missing)}. "
        "Re-run `uv lock` and commit the result."
    )


# --- AC-9 -------------------------------------------------------------------

def test_makefile_recipes_contain_no_bash_isms() -> None:
    # AC-9: recipe shell defaults to /bin/sh (POSIX). Bash-isms are a latent
    # macOS-vs-Linux divergence (e.g., default sh on macOS may be bash, masking
    # the bug locally; on Linux CI the default sh is dash and recipes break).
    text = MAKEFILE.read_text()
    # collect every recipe body across all declared targets
    all_bodies = "".join(
        _recipe_body(t, text) for t in REQUIRED_TARGETS
    )
    assert "[[" not in all_bodies, "Makefile recipes must not use bash `[[`; recipe shell is /bin/sh"
    assert "]]" not in all_bodies, "Makefile recipes must not use bash `]]`"
    assert re.search(r"\bfunction\s+\w+\s*\(\)", all_bodies) is None, \
        "Makefile recipes must not use bash `function NAME()` syntax"


# --- AC-8 (this file is the red anchor; its existence + green is AC-8) -----
# Implicit: pytest discovering and passing this file IS AC-8.
```

The nine tests fail initially: file-existence tests fail with `AssertionError` because no `Makefile` and no `uv.lock` exist; recipe-body tests fail with empty-string returns from `_recipe_body`; the lockstep test fails because `uv.lock` is absent. Run, observe, then proceed to Green.

### Green — make it pass

Write the minimal `Makefile`:

```
.PHONY: bootstrap check lint typecheck test docs fence audit-verify clean

bootstrap:
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install -e ".[dev]"; \
	else \
		python -m pip install -e ".[dev]"; \
	fi

check: lint typecheck test fence

lint:
	ruff check .
	ruff format --check .

# ... etc
```

Generate `uv.lock` via `uv lock` and commit. Resist adding non-required targets, fancy `make`-isms, or extra dependencies.

### Refactor — clean up

- Add a one-line shell comment at the top of `Makefile` explaining target ordering (the `check` chain order from `phase-arch-design.md §Testing strategy / CI gates`).
- Use `@` prefix on every recipe line so output stays clean (matches existing convention readers expect).
- Verify each target's command line is `ruff format`-stable (no trailing whitespace, final newline).
- Confirm that running `make check` invokes the four sub-targets in declared order; `make` won't reorder them but `.PHONY` ensures they always re-run.
- Run `make clean` and confirm it removes `.codegenie/`, `__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, and `htmlcov/` — nothing else.

## Files to touch

| Path | Why |
|---|---|
| `Makefile` | New file — the imperative surface every developer and CI job invokes. |
| `uv.lock` | New file — generated by `uv lock` against `pyproject.toml`; committed for reproducibility. |
| `tests/unit/test_makefile_targets.py` | New file — TDD red anchor; pins the nine required targets and the `bootstrap` dual-path. |

## Out of scope

- **The `fence` test implementation** — handled by S1-05; this story only invokes `pytest tests/unit/test_pyproject_fence.py` from the `fence` target.
- **The mkdocs curated `nav`** — handled by S1-04; `make docs` just calls `mkdocs build --strict`.
- **The `codegenie audit verify` subcommand** — handled by S4-02 (CLI) and S3-06 (verify path); `make audit-verify` just calls the command.
- **CI workflow consumption of these targets** — handled by S1-05 (the `.github/workflows/ci.yml` invokes `make lint`, `make typecheck`, etc.).
- **Pre-commit hook installation** — handled by S1-04.
- **A `make help` target listing available targets** — out of scope; nine targets is small enough to grep.
- **Tab-vs-spaces controversy** — `Makefile` recipe lines *must* be tab-indented (POSIX `make` requirement); the `.editorconfig` from S1-04 sets this expectation.

## Notes for the implementer

- Per `phase-arch-design.md §Open questions deferred to implementation` Q1, both `uv` and `pip` paths must work. Test the `bootstrap` target on a machine *without* `uv` installed at least once before opening the PR — the shell branch is silent on the unhappy path otherwise.
- The `Makefile` recipe shell is `/bin/sh` by default (POSIX), not bash. The `command -v uv >/dev/null 2>&1` form is portable; do **not** use bash-isms like `[[ ... ]]` or `function name() { ... }`.
- `uv.lock` is platform-specific in some edge cases (C-extension wheels). Per ADR-0001, `blake3` is a C-extension; ensure `uv lock` is run on a machine matching the CI runner architecture (`linux/amd64` is the CI target per `phase-arch-design.md §Physical view`). If you must lock on macOS arm64, document that in the PR body — `uv.lock`'s cross-platform behavior is mostly OK but warrants a note.
- `make check`'s chain is `lint → typecheck → test → fence`, not `lint typecheck test docs fence`. `docs` is its own target (because the `docs` CI job runs path-filtered per `phase-arch-design.md §Testing strategy / CI gates`); requiring `docs` to pass on every `check` invocation pushes friction onto contributors who haven't touched docs.
- The `fence` target is wired here to invoke `pytest tests/unit/test_pyproject_fence.py`; the test itself doesn't exist until S1-05 lands. Running `make fence` before S1-05 will fail with "no such file." That's expected for Step 1's intra-step PR ordering — `S1-05` adds the test and `make fence` becomes useful.
- The `audit-verify` target wires `python -m codegenie audit verify`. Phase 0's `__main__.py` from S1-01 has a placeholder `main`; running this target before S4-02 lands will exit immediately. That's fine — the target is a contract for *future* invocation, plus a debugging entry point developers can rely on once the CLI ships.
- Do **not** add a top-level `default:` or `all:` target. `phase-arch-design.md §Development view` only commits to the targets named here; adding a default surface tempts developers to rely on `make` (no args) doing something — surface drift.
- The `clean` target is convenience, not contract — keep it tight: only directories that this project itself creates. Never `rm -rf .git/` or anything outside the repo.
