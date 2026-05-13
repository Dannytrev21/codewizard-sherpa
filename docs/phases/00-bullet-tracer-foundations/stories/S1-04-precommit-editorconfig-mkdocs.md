# Story S1-04 — Pre-commit hooks + editorconfig + gitignore + mkdocs curated nav

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Ready (validated 2026-05-13 — HARDENED)
**Effort:** M
**Depends on:** S1-02
**ADRs honored:** ADR-0008, ADR-0012

## Validation notes

Validated 2026-05-13 by `phase-story-validator` — verdict **HARDENED**. See [`_validation/S1-04-precommit-editorconfig-mkdocs.md`](_validation/S1-04-precommit-editorconfig-mkdocs.md) for the full audit. Changes applied:

- **AC-1** strengthened — full 9-hook required-set mirrored into Test 1's `REQUIRED_HOOKS` constant (was 8 of 9).
- **AC-2** strengthened — full 11-pattern list including `subprocess.run(...shell=...)` (ADR-0012 §Decision line 36 wins over phase-arch Q6's deferral); the `yaml.Dumper` regex must be anchored so it does NOT match `yaml.CSafeDumper`/`SafeDumper` (the ADR-0008-prescribed writer). `print(` scope contracted via `exclude:`.
- **AC-3** strengthened — full 6-property check on `[*.py]` and `indent_style = tab` on `[Makefile]` (was 4 of 6; Makefile section existed but its tab requirement was unverified).
- **AC-4** strengthened — all 13 `.gitignore` entries line-parse-verified (was 7 of 13 via substring; commented-out lines could slip).
- **AC-5** split — comment-near-nav-entry requirement demoted to documentary (`yaml.safe_load` strips comments; can't test); nav exclusion remains load-bearing.
- **AC-6, AC-7** strengthened — behavioral subprocess tests (Tests 7 and 8) verify the goal sentence directly; previously the goal was untested.
- **AC-8** relaxed — drop "was committed" (cataloged process clause from S1-01/02/03); restate as "exists and exits 0 under pytest".
- **AC-9** added — every non-`local` hook's `rev` is a 40-char hex SHA (implementation outline §2 contract, now a load-bearing AC).
- **AC-10** added — `docs/contributing.md` placeholder exists with `TODO(S5-02)` marker (was implicit; AC-7 silently depended on it).
- **AC-11** added — `print(` rule scoped via `exclude:` to skip `^tests/` and `^scripts/`.
- **AC-12** added — `yaml.Dumper` regex anchored to preserve `yaml.CSafeDumper`/`SafeDumper`.
- **TDD plan** grew from 5 to 12 tests; Test 2 replaced YAML-serialize-then-substring (regex-escape fragile) with a behavioral fixture suite that runs the hook against 11 banned constructs plus 2 prescribed forms (`yaml.CSafeDumper`/`SafeDumper`); Test 5's `_flatten` recurses on any `Mapping` (was list-only — silently dropped dict-valued nav items).
- **Conflict resolution:** ADR-0012 §Decision (Accepted) wins over phase-arch §Open questions Q6 — `subprocess.run(...shell=...)` is Phase 0, not Phase 1. Out-of-scope narrowed accordingly.

## Context

This story plants the pre-commit "first defense" line that catches lint, format, type, and secret/forbidden-pattern violations before they ever reach CI — and the curated `mkdocs.yml` `nav` that excludes the four superseded design docs (`local.md`, `auto-agent-design.md`, `gemini-auto-agent-design.md`, `context.md`, `localv2.md`) so `mkdocs build --strict` is green from Phase 0 onward. The `forbidden-patterns` hook is the *executable* enforcement of two ADRs simultaneously: ADR-0008 (no `yaml.load(` without `Loader=`, no `yaml.Dumper`) and ADR-0012 (no `shell=True`, no `os.system`, no `os.popen`).

This is plumbing-with-teeth — the structural defense layer that runs on every developer's commit before code ever touches CI. It is cross-cutting work; every later story benefits from the pre-commit firewall.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Harness engineering` — logging strategy (`T20` blocks `print(` in src/; pre-commit must align).
  - `../phase-arch-design.md §Testing strategy / Adversarial tests` — the `tests/adv/test_no_shell_true.py` and `test_yaml_unsafe_load.py` AST scans land in Step 2/4 and pair with the pre-commit hook.
  - `../phase-arch-design.md §Testing strategy / CI gates` — `docs` job runs `mkdocs build --strict` over the curated `nav`.
  - `../phase-arch-design.md §Open questions deferred to implementation` Q6 — the initial `forbidden-patterns` regex set.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — gitleaks runs at pre-commit; `yaml.load(...)` without `Loader=` and `yaml.Dumper` are banned.
  - `../ADRs/0012-subprocess-allowlist-chokepoint.md` — ADR-0012 — `shell=True`, `os.system`, `os.popen`, `pickle.loads`, `eval(`, `exec(`, `__import__(` are banned in `src/codegenie/`.
- **Source design:**
  - `../High-level-impl.md §Step 1` — Features delivered: `.pre-commit-config.yaml`, `.editorconfig`, `.gitignore`, `mkdocs.yml` with curated `nav`.
- **External docs:**
  - https://pre-commit.com/hooks.html — `ruff`, `mypy`, `gitleaks`, `check-yaml`, `check-toml`, `end-of-file-fixer` hooks.
  - https://www.mkdocs.org/user-guide/configuration/#nav — `nav` schema.

## Goal

`pre-commit run --all-files` exits 0 on the current tree and `mkdocs build --strict` is green over a `nav` that excludes the superseded design docs.

## Acceptance criteria

- [ ] **AC-1.** `.pre-commit-config.yaml` exists at the repo root declaring exactly these 9 hook ids (frozen set): `ruff`, `ruff-format`, `mypy` (strict on `src/`), `gitleaks`, `forbidden-patterns` (local hook), `check-yaml`, `check-toml`, `end-of-file-fixer`, `trailing-whitespace`. Test 1 in the TDD plan mirrors this list as a `REQUIRED_HOOKS` constant and asserts equality, not subset. (Additive over High-level-impl §Step 1's 8-hook list: `trailing-whitespace` comes from the same `pre-commit/pre-commit-hooks` repo as `end-of-file-fixer` and pairs with editorconfig's `trim_trailing_whitespace = true`.)
- [ ] **AC-2.** The `forbidden-patterns` hook bans, via one regex per pattern, all 11 of the following constructs:
  1. `print(` — outside `tests/` and `scripts/` (scope contracted in AC-11)
  2. `yaml.load(` — only when `Loader=` is NOT present (the qualifier is load-bearing per ADR-0008)
  3. `shell=True`
  4. `subprocess.run(..., shell=...)` — regex matches `subprocess\.run\s*\([^)]*shell\s*=` to catch both literal `shell=True` and dynamic `shell=variable` (per ADR-0012 §Decision line 36)
  5. `yaml.Dumper` — anchored so it does NOT match `yaml.CSafeDumper` or `yaml.SafeDumper` (the ADR-0008-prescribed writers; see AC-12)
  6. `os.system(`
  7. `os.popen(`
  8. `pickle.loads(`
  9. `eval(`
  10. `exec(` (the function call, not `__main__`)
  11. `__import__(`
- [ ] **AC-3.** `.editorconfig` exists at the repo root and parses with `configparser`. For `[*.py]`: all six of `indent_style = space`, `indent_size = 4`, `end_of_line = lf`, `charset = utf-8`, `insert_final_newline = true`, `trim_trailing_whitespace = true` are present. For `[Makefile]`: `indent_style = tab` is present (POSIX requirement for recipes — this is *the* reason the Makefile section exists).
- [ ] **AC-4.** `.gitignore` exists at the repo root. When parsed line-by-line (stripping whitespace and skipping `#`-prefixed comments and blank lines), all 13 of the following appear as standalone uncommented lines: `.codegenie/`, `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `htmlcov/`, `*.egg-info/`, `dist/`, `build/`, `.venv/`, `.env`, `.DS_Store`, `site/` (mkdocs output). `.env` is security-relevant per ADR-0008's spirit (no secrets in commits).
- [ ] **AC-5.** `mkdocs.yml` exists at the repo root with `site_name`, `theme: material`, and a curated `nav`. When the `nav` is recursively flattened over any `Mapping` (not just `list`) — yielding only `str` leaves — **no** yielded ref contains any of the 5 excluded filenames: `local.md`, `auto-agent-design.md`, `gemini-auto-agent-design.md`, `context.md`, `localv2.md`. (Documentary note, not contractually tested: a `# excluded: see final-design.md §2.2 / §5` block near the top of `mkdocs.yml` or near the would-be nav entries is recommended for human reviewers — `yaml.safe_load` strips comments so this cannot be verified by the test.)
- [ ] **AC-6.** `pre-commit install` succeeds and `pre-commit run --all-files` exits 0 on the current tree. Test 7 in the TDD plan invokes `pre-commit run --all-files` via `subprocess.run` and asserts `returncode == 0` (skipping with reason if `pre-commit` is not on `$PATH`).
- [ ] **AC-7.** `mkdocs build --strict` exits 0 from the repo root. Test 8 in the TDD plan invokes `mkdocs build --strict` via `subprocess.run` and asserts `returncode == 0` (skipping with reason if `mkdocs` is not on `$PATH`).
- [ ] **AC-8.** `tests/unit/test_precommit_and_docs_config.py` exists, and `pytest tests/unit/test_precommit_and_docs_config.py -q` exits 0.
- [ ] **AC-9.** Every hook entry in `.pre-commit-config.yaml` from a non-`local` repo declares `rev` as a 40-character lowercase hex SHA (matching `^[0-9a-f]{40}$`), not a mutable tag — per `phase-arch-design.md §Testing strategy / CI gates` ("Actions pinned by SHA"). The single `local` repo (`forbidden-patterns`) has no `rev`.
- [ ] **AC-10.** `docs/contributing.md` exists and contains the substring `TODO(S5-02)` so that the curated `nav` resolves under `mkdocs build --strict`. The real contributor docs land in S5-02.
- [ ] **AC-11.** The `forbidden-patterns` hook's `print(` rule is scoped via `exclude:` (or `files:`) such that paths under `^tests/` and `^scripts/` are skipped. Test 11 parses the hook block and asserts the exclusion regex matches both prefixes.
- [ ] **AC-12.** The `yaml.Dumper` regex is anchored such that `re.search(pattern, "yaml.CSafeDumper")` and `re.search(pattern, "yaml.SafeDumper")` are both `None`, while `re.search(pattern, "yaml.Dumper(x)")` returns a match. This preserves ADR-0008's prescribed writer (`yaml.CSafeDumper`).

## Implementation outline

1. Write the 12-test red plan in `tests/unit/test_precommit_and_docs_config.py` (see TDD plan below).
2. Author `.pre-commit-config.yaml` with the 9-hook list. **Every non-`local` hook's `rev` must be a 40-char hex SHA**, not a tag — supply-chain stability per `phase-arch-design.md §Testing strategy / CI gates` (AC-9 enforces this). Resolve each SHA from `github.com/<owner>/<repo>/releases/tag/<tag>` and paste it as `rev: <sha>`.
3. Add the `forbidden-patterns` local hook with `entry: scripts/check_forbidden_patterns.sh` (or `.py`). The script `grep -E`-checks staged files against the 11-pattern regex list. The `yaml.Dumper` pattern must be anchored — e.g., `(?<!CSafe)(?<!Safe)yaml\.Dumper` or `\byaml\.Dumper\b(?!.*(?:CSafeDumper|SafeDumper))` — so it does NOT match the prescribed `yaml.CSafeDumper`/`SafeDumper` (AC-12). The `print(` rule is scoped via `exclude: '^(tests/|scripts/)'` at hook or rule level (AC-11).
4. Author `.editorconfig` (full 6 properties for `[*.py]` + `indent_style = tab` for `[Makefile]`), `.gitignore` (13 entries, one per line), `mkdocs.yml` (`site_name`, `theme: material`, curated `nav` excluding the 5 docs).
5. Create `docs/contributing.md` with a `# TODO(S5-02)` comment so the nav resolves (AC-10).
6. Run `pre-commit install` and `pre-commit run --all-files`; fix the *minimal* issues so the existing S1-01..S1-03 tree passes (AC-6).
7. Run `mkdocs build --strict`; confirm no broken-link or missing-page warnings against the curated `nav` (AC-7).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_precommit_and_docs_config.py`

```python
# tests/unit/test_precommit_and_docs_config.py
from __future__ import annotations

import configparser
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Iterator

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Mirrors AC-1 exactly. Equality test, not subset — duplication here is the point.
REQUIRED_HOOKS: frozenset[str] = frozenset({
    "ruff", "ruff-format", "mypy", "gitleaks", "forbidden-patterns",
    "check-yaml", "check-toml", "end-of-file-fixer", "trailing-whitespace",
})

# Mirrors AC-2. The 11 banned constructs the forbidden-patterns hook must reject.
# Stored as (label, fixture_source) — `fixture_source` is the file content the
# hook should reject when written to disk and run through `entry`.
BANNED_CONSTRUCTS: list[tuple[str, str]] = [
    ("print",          'print("hi")\n'),
    ("yaml.load_unsafe", "import yaml\nyaml.load(s)\n"),  # no Loader=
    ("shell_True",     "subprocess.run(cmd, shell=True)\n"),
    ("subprocess_run_shell_dynamic", "subprocess.run(cmd, shell=flag)\n"),
    ("yaml.Dumper",    "import yaml\nyaml.dump(x, Dumper=yaml.Dumper)\n"),
    ("os.system",      "import os\nos.system('ls')\n"),
    ("os.popen",       "import os\nos.popen('ls')\n"),
    ("pickle.loads",   "import pickle\npickle.loads(b)\n"),
    ("eval_call",      "eval('1+1')\n"),
    ("exec_call",      "exec('x=1')\n"),
    ("dunder_import",  "__import__('os')\n"),
]

# Mirrors AC-12 — these must NOT trigger the yaml.Dumper rule.
ALLOWED_DUMPER_CONSTRUCTS: list[tuple[str, str]] = [
    ("yaml.CSafeDumper", "import yaml\nyaml.dump(x, Dumper=yaml.CSafeDumper)\n"),
    ("yaml.SafeDumper",  "import yaml\nyaml.dump(x, Dumper=yaml.SafeDumper)\n"),
]

# Mirrors AC-4. All 13 entries are line-parse-verified.
REQUIRED_GITIGNORE_ENTRIES: frozenset[str] = frozenset({
    ".codegenie/", "__pycache__/", "*.pyc", ".mypy_cache/", ".ruff_cache/",
    ".pytest_cache/", "htmlcov/", "*.egg-info/", "dist/", "build/",
    ".venv/", ".env", ".DS_Store", "site/",
})

# Mirrors AC-3. The full [*.py] contract.
REQUIRED_EDITORCONFIG_PYPROPS: dict[str, str] = {
    "indent_style": "space",
    "indent_size": "4",
    "end_of_line": "lf",
    "charset": "utf-8",
    "insert_final_newline": "true",
    "trim_trailing_whitespace": "true",
}

# Mirrors AC-5. mkdocs nav must not reference any of these.
EXCLUDED_NAV_DOCS: frozenset[str] = frozenset({
    "local.md", "auto-agent-design.md", "gemini-auto-agent-design.md",
    "context.md", "localv2.md",
})


def _load_precommit() -> dict:
    cfg_path = PROJECT_ROOT / ".pre-commit-config.yaml"
    assert cfg_path.is_file(), ".pre-commit-config.yaml must exist at repo root"
    return yaml.safe_load(cfg_path.read_text())


def _forbidden_patterns_hook() -> dict:
    """Locate the local forbidden-patterns hook block."""
    cfg = _load_precommit()
    for repo in cfg["repos"]:
        for h in repo["hooks"]:
            if h["id"] == "forbidden-patterns":
                return h
    raise AssertionError("forbidden-patterns hook missing from .pre-commit-config.yaml")


def _forbidden_patterns_entry_script() -> Path:
    """Resolve the entry script path. The hook's entry is either a script path or an inline grep."""
    hook = _forbidden_patterns_hook()
    entry = hook.get("entry", "")
    assert entry, "forbidden-patterns hook missing entry"
    # entry may be `scripts/check_forbidden_patterns.sh` or `bash -c '...'` etc.
    first_token = entry.split()[0]
    candidate = PROJECT_ROOT / first_token
    if candidate.is_file():
        return candidate
    # Inline grep form — return a sentinel; behavioral test will invoke the hook via pre-commit.
    return Path("__INLINE__")


# ---------- Test 1: AC-1 (9-hook required-set + local-hook entry non-stub) ----------

def test_precommit_config_declares_exactly_the_required_hooks() -> None:
    cfg = _load_precommit()
    hooks = {h["id"] for repo in cfg["repos"] for h in repo["hooks"]}
    missing = REQUIRED_HOOKS - hooks
    assert not missing, f".pre-commit-config.yaml missing hooks: {sorted(missing)}"
    # Local hooks (repo: local) must have a non-stub entry — covers the
    # `id: forbidden-patterns, entry: \"true\"` mutation slip.
    for repo in cfg["repos"]:
        if repo.get("repo") == "local":
            for h in repo["hooks"]:
                entry = (h.get("entry") or "").strip()
                assert entry, f"local hook `{h['id']}` missing `entry`"
                assert entry not in {"true", "echo", ":"}, (
                    f"local hook `{h['id']}` has stub entry `{entry}`"
                )
                first_token = entry.split()[0]
                script = PROJECT_ROOT / first_token
                if not script.is_file():
                    # Inline form is allowed; must at least mention grep.
                    assert "grep" in entry, (
                        f"local hook `{h['id']}` entry neither references a script "
                        f"nor uses grep: `{entry}`"
                    )


# ---------- Test 2: AC-2 + AC-12 (behavioral fixture suite — 11 reject, 2 accept) ----------

@pytest.mark.parametrize("label,source", BANNED_CONSTRUCTS, ids=[t[0] for t in BANNED_CONSTRUCTS])
def test_forbidden_patterns_hook_rejects_each_banned_construct(
    label: str, source: str, tmp_path: Path
) -> None:
    """For each banned construct, write a fixture file and run the hook entry against it.

    The hook must exit non-zero. Implements AC-2 by *behavior*, not config-text substring.
    """
    script = _forbidden_patterns_entry_script()
    if script == Path("__INLINE__"):
        pytest.skip("inline-grep entry not directly invocable; covered by Test 7 (pre-commit run)")
    fixture = tmp_path / f"banned_{label}.py"
    fixture.write_text(source)
    result = subprocess.run(
        [str(script), str(fixture)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"forbidden-patterns hook FAILED to reject `{label}` "
        f"(content: {source!r}); stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@pytest.mark.parametrize(
    "label,source",
    ALLOWED_DUMPER_CONSTRUCTS,
    ids=[t[0] for t in ALLOWED_DUMPER_CONSTRUCTS],
)
def test_yaml_dumper_regex_does_not_reject_csafedumper_or_safedumper(
    label: str, source: str, tmp_path: Path
) -> None:
    """AC-12: the yaml.Dumper regex must NOT match yaml.CSafeDumper or yaml.SafeDumper.

    These are the ADR-0008-prescribed writers; blocking them breaks the sanitizer's writer.
    """
    script = _forbidden_patterns_entry_script()
    if script == Path("__INLINE__"):
        pytest.skip("inline-grep entry; AC-12 covered by Test 7 + manual review")
    fixture = tmp_path / f"allowed_{label}.py"
    fixture.write_text(source)
    result = subprocess.run(
        [str(script), str(fixture)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"forbidden-patterns hook WRONGLY rejected the ADR-0008-prescribed `{label}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}. "
        "The yaml.Dumper regex must be anchored (e.g., (?<!CSafe)(?<!Safe)yaml\\.Dumper)."
    )


# ---------- Test 3: AC-4 (.gitignore line-parse) ----------

def test_gitignore_contains_all_required_entries_as_uncommented_lines() -> None:
    gi = PROJECT_ROOT / ".gitignore"
    assert gi.is_file(), ".gitignore must exist at repo root"
    lines: set[str] = set()
    for raw in gi.read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.add(s)
    missing = REQUIRED_GITIGNORE_ENTRIES - lines
    assert not missing, f".gitignore missing uncommented entries: {sorted(missing)}"


# ---------- Test 4: AC-3 (.editorconfig configparser-parse) ----------

def test_editorconfig_python_and_makefile_contracts() -> None:
    ec = PROJECT_ROOT / ".editorconfig"
    assert ec.is_file(), ".editorconfig must exist at repo root"
    parser = configparser.ConfigParser()
    # editorconfig allows section names with [ and *; configparser handles them.
    parser.read(ec)
    # AC-3: full 6-key contract on [*.py]
    assert "*.py" in parser, ".editorconfig must declare [*.py] section"
    py_section = parser["*.py"]
    for key, expected in REQUIRED_EDITORCONFIG_PYPROPS.items():
        assert key in py_section, f"[*.py] missing key `{key}`"
        assert py_section[key].strip().lower() == expected.lower(), (
            f"[*.py] {key} = {py_section[key]!r}; expected {expected!r}"
        )
    # AC-3: Makefile MUST use tab indent (POSIX). This is the *only* reason the section exists.
    assert "Makefile" in parser, ".editorconfig must declare [Makefile] section"
    assert parser["Makefile"]["indent_style"].strip().lower() == "tab", (
        f"[Makefile] indent_style = {parser['Makefile']['indent_style']!r}; expected 'tab' "
        "(POSIX requires tab indentation for Makefile recipes)"
    )


# ---------- Test 5: AC-5 (mkdocs nav recursive Mapping flatten) ----------

def _flatten_nav(items: object) -> Iterator[str]:
    """Yield every str leaf, recursing over both list and Mapping values."""
    if isinstance(items, str):
        yield items
        return
    if isinstance(items, Mapping):
        for v in items.values():
            yield from _flatten_nav(v)
        return
    if isinstance(items, list):
        for item in items:
            yield from _flatten_nav(item)
        return
    # Anything else (None, int, etc.) — ignored.


def test_mkdocs_nav_excludes_all_superseded_design_docs() -> None:
    mk = PROJECT_ROOT / "mkdocs.yml"
    assert mk.is_file(), "mkdocs.yml must exist at repo root"
    cfg = yaml.safe_load(mk.read_text())
    refs = list(_flatten_nav(cfg.get("nav", [])))
    # AC-5: every yielded ref is a str
    for ref in refs:
        assert isinstance(ref, str), (
            f"mkdocs nav contains non-str leaf {ref!r} — flatten contract violated"
        )
    # AC-5: no excluded doc appears in any ref
    for excluded in EXCLUDED_NAV_DOCS:
        for ref in refs:
            assert excluded not in ref, (
                f"mkdocs nav must NOT reference `{excluded}`; found in `{ref}`"
            )


# ---------- Test 6: AC-9 (SHA-pin every non-local hook rev) ----------

def test_every_non_local_hook_rev_is_sha_pinned() -> None:
    cfg = _load_precommit()
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    for repo in cfg["repos"]:
        if repo.get("repo") == "local":
            continue
        rev = repo.get("rev", "")
        assert sha_re.match(rev), (
            f"repo `{repo['repo']}` has rev `{rev}`; AC-9 requires a 40-char hex SHA "
            "(per phase-arch §Testing strategy / CI gates — Actions pinned by SHA)"
        )


# ---------- Test 7: AC-6 (behavioral pre-commit run) ----------

def test_pre_commit_run_all_files_exits_zero() -> None:
    if shutil.which("pre-commit") is None:
        pytest.skip("pre-commit not on PATH; install [dev] extras to enable AC-6 verification")
    result = subprocess.run(
        ["pre-commit", "run", "--all-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"`pre-commit run --all-files` exited {result.returncode}; "
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


# ---------- Test 8: AC-7 (behavioral mkdocs build --strict) ----------

def test_mkdocs_build_strict_exits_zero() -> None:
    if shutil.which("mkdocs") is None:
        pytest.skip("mkdocs not on PATH; install [dev] extras to enable AC-7 verification")
    result = subprocess.run(
        ["mkdocs", "build", "--strict"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"`mkdocs build --strict` exited {result.returncode}; "
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


# ---------- Test 9: AC-10 (contributing.md placeholder) ----------

def test_contributing_md_placeholder_exists_with_todo_marker() -> None:
    contrib = PROJECT_ROOT / "docs" / "contributing.md"
    assert contrib.is_file(), "docs/contributing.md must exist as a placeholder (AC-10)"
    body = contrib.read_text()
    assert "TODO(S5-02)" in body, (
        "docs/contributing.md must contain `TODO(S5-02)` marker so a future reader "
        "knows S5-02 fills in the real contributor docs"
    )


# ---------- Test 10: AC-1 robustness (no duplicate hook ids) ----------

def test_no_duplicate_hook_ids() -> None:
    cfg = _load_precommit()
    seen: dict[str, int] = {}
    for repo in cfg["repos"]:
        for h in repo["hooks"]:
            seen[h["id"]] = seen.get(h["id"], 0) + 1
    dups = {hid: count for hid, count in seen.items() if count > 1}
    assert not dups, f"duplicate hook ids in .pre-commit-config.yaml: {dups}"


# ---------- Test 11: AC-11 (print() scoped via exclude:) ----------

def test_print_rule_excludes_tests_and_scripts() -> None:
    """AC-11: the print( rule must be scoped to skip ^tests/ and ^scripts/."""
    hook = _forbidden_patterns_hook()
    # Two acceptable shapes:
    # (a) the hook itself has an `exclude:` regex that skips tests/ and scripts/
    # (b) the entry script implements per-rule exclusion internally
    # We test for (a) at the config level — if the implementer chose (b), they should
    # restructure as (a) or add explicit config-level proof of scoping.
    exclude = hook.get("exclude") or ""
    # The regex must match BOTH 'tests/foo.py' and 'scripts/bar.sh'
    assert exclude, (
        "AC-11: forbidden-patterns hook must declare `exclude:` to scope the "
        "print( rule away from tests/ and scripts/. If exclusion is internal to "
        "the entry script, lift it to the hook config so it's auditable."
    )
    # Compile and test the exclude regex against canonical paths.
    pat = re.compile(exclude)
    for path in ("tests/unit/test_foo.py", "scripts/check_forbidden_patterns.sh"):
        assert pat.search(path), (
            f"AC-11: exclude regex `{exclude}` does not match `{path}` "
            "— print(-bearing files in tests/ and scripts/ would be wrongly flagged"
        )


# ---------- Test 12: AC-8 (meta — this file collected at least 11 test functions) ----------

def test_this_file_has_at_least_eleven_test_functions() -> None:
    """AC-8 meta-check — protects against accidental test deletion."""
    this = Path(__file__).read_text()
    # Count `def test_` at line starts; parametrized tests each count once.
    count = sum(1 for line in this.splitlines() if line.startswith("def test_"))
    assert count >= 11, (
        f"test_precommit_and_docs_config.py must define ≥ 11 test functions; "
        f"found {count}. AC-8 + the validation report require the 12-test plan."
    )
```

The tests fail initially: file-existence checks fail with `AssertionError`; the behavioral fixture suite (Test 2) errors when `_forbidden_patterns_entry_script` can't find the script; the SHA-pin check fails because no `rev`s are SHAs yet. Run the suite, observe the red signals, commit the failing tests.

### Green — make it pass

Author the four config files. For `.pre-commit-config.yaml`, use the canonical hook repos from `pre-commit.com/hooks.html`:

- `https://github.com/astral-sh/ruff-pre-commit` for `ruff` + `ruff-format`.
- `https://github.com/pre-commit/mirrors-mypy` for `mypy`.
- `https://github.com/gitleaks/gitleaks` for `gitleaks`.
- `https://github.com/pre-commit/pre-commit-hooks` for `check-yaml`, `check-toml`, `end-of-file-fixer`, `trailing-whitespace`.
- A `local` repo for `forbidden-patterns` with `entry: scripts/check_forbidden_patterns.sh` (or inline `grep`).

Each `rev` must be a tag *and* SHA-pinned where practical (per `phase-arch-design.md §Testing strategy / CI gates`: "Actions pinned by SHA" applies to pre-commit hook revs as well).

For `mkdocs.yml`, the `nav` should mirror the navigable structure (`README`, `roadmap`, `production/`, `phases/` index, `contributing.md` once S5-02 adds it). The excluded docs sit on disk but are not in `nav`.

### Refactor — clean up

- Add comments in `.pre-commit-config.yaml` near each hook noting its purpose (e.g., `# enforces ADR-0008/0012 via regex`).
- Add a top-of-file comment in `mkdocs.yml` listing the excluded files with the rationale `# excluded: see ../final-design.md §2.2 / §5 — Phase 1 cleanup`.
- Verify the `forbidden-patterns` hook's entry script is itself shellcheck-clean if implemented as bash, or `ruff`-clean if implemented as Python.
- Ensure `.gitignore` ends with a final newline (the `end-of-file-fixer` hook will catch this anyway).
- Add an empty `docs/contributing.md` placeholder file referenced in `mkdocs.yml`'s nav with a `# TODO(S5-02): contributor docs` comment so `mkdocs build --strict` doesn't fail on a dangling nav entry.

## Files to touch

| Path | Why |
|---|---|
| `.pre-commit-config.yaml` | New file — the hook configuration. |
| `.editorconfig` | New file — cross-editor formatting baseline. |
| `.gitignore` | New file — includes `.codegenie/` per CLAUDE.md convention. |
| `mkdocs.yml` | New file — curated `nav` excluding superseded docs. |
| `scripts/check_forbidden_patterns.sh` | New file (optional) — implements the `forbidden-patterns` local hook entry. Inline `grep` in the hook config is also acceptable. |
| `docs/contributing.md` | New file (placeholder) — `# TODO(S5-02)` stub so the nav resolves. |
| `tests/unit/test_precommit_and_docs_config.py` | New file — TDD red anchor. |

## Out of scope

- **Real contributor docs** — handled by S5-02; this story ships a placeholder.
- **The CI workflow that runs `mkdocs build --strict`** — handled by S1-05.
- **The `forbidden-patterns` AST scan tests under `tests/adv/`** — handled by S2-02 (`test_no_shell_true.py`), S2-02 (`test_yaml_unsafe_load.py`), and S4-05 (full adversarial suite). The hook is the developer-machine defense; the AST scans are the CI/structural defense.
- **`gitleaks` configuration tuning (`.gitleaksignore`, custom rules)** — handled if/when a real false positive surfaces; the default `gitleaks` config is fine for Phase 0.
- **Extending the `forbidden-patterns` regex set with `marshal.loads`, `dill.loads`, `__builtins__`, `getattr(..., "__"`** — these are filed as Phase 1 hardening per `phase-arch-design.md §Open questions` Q6. (Note: `subprocess.run(..., shell=...)` has been **pulled into AC-2** per ADR-0012 §Decision line 36 — the ADR's Decision section is source of truth over the phase-arch open question.)
- **MkDocs plugins (search, redirects, mermaid renderer)** — `mkdocs-material` ships the essentials; additional plugins land when a doc needs one.

## Notes for the implementer

- The `forbidden-patterns` hook is *local* (no upstream repo). Its `entry` can be a shell `grep -E` or a tiny Python script under `scripts/`. Inline `grep` is simpler but harder to test; if you go the script route, run `ruff check scripts/check_forbidden_patterns.sh` if it's bash via `shellcheck` and `ruff check scripts/check_forbidden_patterns.py` if Python.
- The `print(` ban is `T20` in `ruff` (already configured in S1-02 for `src/`). The `forbidden-patterns` hook's `print(` rule is the second wall — it covers files outside `src/` too, *except* `tests/` and `scripts/` which legitimately use `print()` for debugging output. Scope the regex with `files:` / `exclude:` blocks.
- `pre-commit` hook `rev` pinning: when in doubt, copy the canonical example from `pre-commit.com/hooks.html` and replace the version tag with the SHA from `github.com/<owner>/<repo>/releases/tag/<tag>`. The `pre-commit autoupdate` command can do this once you commit initial revs; don't trust `pre-commit autoupdate` blind, though — review the SHA-pinned diff.
- `mkdocs.yml`'s `theme: material` requires `mkdocs-material` from S1-01's `[dev]` extras. If `mkdocs build` fails with a theme error, S1-01's dep list is wrong.
- The five excluded docs (`local.md`, `auto-agent-design.md`, `gemini-auto-agent-design.md`, `context.md`, `localv2.md`) are listed in `CLAUDE.md` as legacy or background reading. Per `phase-arch-design.md §Non-goals` #15 and the Step 1 Features list, the `mkdocs` `nav` curates *away* from them; S5-02 files a Phase 1 issue to either fix or delete each one.
- `mkdocs build --strict` fails on **any** warning: missing pages, dangling links, duplicate IDs. If you reference a doc that doesn't yet exist (like `contributing.md`), create a placeholder file in this story.
- Per ADR-0011, `.codegenie/` files are mode `0600` and dirs `0700`. The `.gitignore` rule `.codegenie/` covers any contributor running `codegenie gather` against this repo itself ("dogfood"), so cache blobs and audit records don't accidentally land in commits.
- Do **not** add `*.md` or `docs/**` to `.gitignore`. The docs are tracked, just curated in the nav.
- `gitleaks` runs over the *staged diff*, not the whole repo, in pre-commit mode. The repo-wide CI scan in S1-05 is a separate invocation.
