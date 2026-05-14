"""Pre-commit + editorconfig + gitignore + mkdocs nav contract (story S1-04).

TDD red anchor. Pins the structural defenses that run on every developer's
commit before code reaches CI: the 9-hook ``.pre-commit-config.yaml``
(including the ``forbidden-patterns`` local hook that enforces ADR-0008 and
ADR-0012 by regex), the ``.editorconfig`` cross-editor baseline (POSIX
``indent_style = tab`` on the Makefile is *the* reason its section exists),
the ``.gitignore`` line-set, and the curated ``mkdocs.yml`` ``nav`` that
excludes the five superseded design docs so ``mkdocs build --strict`` is
green from Phase 0 onward.

Behavioral tests (`Test 2`) write fixture files and shell out to the hook's
entry script — substring-checking the YAML config is fragile against
escape sequences, so we verify by behavior.
"""

from __future__ import annotations

import configparser
import re
import shutil
import subprocess
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Mirrors AC-1 exactly. Equality test, not subset — duplication here is the point.
REQUIRED_HOOKS: frozenset[str] = frozenset(
    {
        "ruff",
        "ruff-format",
        "mypy",
        "gitleaks",
        "forbidden-patterns",
        "check-yaml",
        "check-toml",
        "end-of-file-fixer",
        "trailing-whitespace",
    }
)

# Mirrors AC-2. The 11 banned constructs the forbidden-patterns hook must reject.
# Each tuple is (label, fixture_source) — fixture_source is the file content the
# hook should reject when written to disk and run through `entry`.
BANNED_CONSTRUCTS: list[tuple[str, str]] = [
    ("print", 'print("hi")\n'),
    ("yaml.load_unsafe", "import yaml\nyaml.load(s)\n"),  # no Loader=
    ("shell_True", "subprocess.run(cmd, shell=True)\n"),
    ("subprocess_run_shell_dynamic", "subprocess.run(cmd, shell=flag)\n"),
    ("yaml.Dumper", "import yaml\nyaml.dump(x, Dumper=yaml.Dumper)\n"),
    ("os.system", "import os\nos.system('ls')\n"),
    ("os.popen", "import os\nos.popen('ls')\n"),
    ("pickle.loads", "import pickle\npickle.loads(b)\n"),
    ("eval_call", "eval('1+1')\n"),
    ("exec_call", "exec('x=1')\n"),
    ("dunder_import", "__import__('os')\n"),
]

# Mirrors AC-12 — these must NOT trigger the yaml.Dumper rule.
ALLOWED_DUMPER_CONSTRUCTS: list[tuple[str, str]] = [
    ("yaml.CSafeDumper", "import yaml\nyaml.dump(x, Dumper=yaml.CSafeDumper)\n"),
    ("yaml.SafeDumper", "import yaml\nyaml.dump(x, Dumper=yaml.SafeDumper)\n"),
]

# Mirrors AC-4. All 13 entries are line-parse-verified.
REQUIRED_GITIGNORE_ENTRIES: frozenset[str] = frozenset(
    {
        ".codegenie/",
        "__pycache__/",
        "*.pyc",
        ".mypy_cache/",
        ".ruff_cache/",
        ".pytest_cache/",
        "htmlcov/",
        "*.egg-info/",
        "dist/",
        "build/",
        ".venv/",
        ".env",
        ".DS_Store",
        "site/",
    }
)

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
EXCLUDED_NAV_DOCS: frozenset[str] = frozenset(
    {
        "local.md",
        "auto-agent-design.md",
        "gemini-auto-agent-design.md",
        "context.md",
        "localv2.md",
    }
)


def _load_precommit() -> dict[str, object]:
    cfg_path = PROJECT_ROOT / ".pre-commit-config.yaml"
    assert cfg_path.is_file(), ".pre-commit-config.yaml must exist at repo root"
    loaded = yaml.safe_load(cfg_path.read_text())
    assert isinstance(loaded, dict), ".pre-commit-config.yaml must parse as a mapping"
    return loaded


def _forbidden_patterns_hook() -> dict[str, object]:
    """Locate the local forbidden-patterns hook block."""
    cfg = _load_precommit()
    repos = cfg["repos"]
    assert isinstance(repos, list)
    for repo in repos:
        for h in repo["hooks"]:
            if h["id"] == "forbidden-patterns":
                assert isinstance(h, dict)
                return h
    raise AssertionError("forbidden-patterns hook missing from .pre-commit-config.yaml")


def _forbidden_patterns_entry_script() -> Path:
    """Resolve the entry script path. The hook's entry is a script path."""
    hook = _forbidden_patterns_hook()
    entry = str(hook.get("entry", "") or "")
    assert entry, "forbidden-patterns hook missing entry"
    first_token = entry.split()[0]
    candidate = PROJECT_ROOT / first_token
    if candidate.is_file():
        return candidate
    # Inline form — return a sentinel; behavioral test will invoke via pre-commit.
    return Path("__INLINE__")


# ---------- Test 1: AC-1 (9-hook required-set + local-hook entry non-stub) ----------


def test_precommit_config_declares_exactly_the_required_hooks() -> None:
    cfg = _load_precommit()
    repos = cfg["repos"]
    assert isinstance(repos, list)
    hooks = {h["id"] for repo in repos for h in repo["hooks"]}
    missing = REQUIRED_HOOKS - hooks
    assert not missing, f".pre-commit-config.yaml missing hooks: {sorted(missing)}"
    # Local hooks (repo: local) must have a non-stub entry — covers the
    # `id: forbidden-patterns, entry: \"true\"` mutation slip.
    for repo in repos:
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
        pytest.skip("inline-grep entry not directly invocable; covered by Test 7")
    fixture = tmp_path / f"banned_{label}.py"
    fixture.write_text(source)
    result = subprocess.run(
        [str(script), str(fixture)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
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
        check=False,
    )
    assert result.returncode == 0, (
        f"forbidden-patterns hook WRONGLY rejected the ADR-0008-prescribed `{label}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}. "
        "The yaml.Dumper regex must be anchored "
        "(e.g., (?<!CSafe)(?<!Safe)yaml\\.Dumper)."
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
    parser.read(ec)
    # AC-3: full 6-key contract on [*.py]
    assert "*.py" in parser, ".editorconfig must declare [*.py] section"
    py_section = parser["*.py"]
    for key, expected in REQUIRED_EDITORCONFIG_PYPROPS.items():
        assert key in py_section, f"[*.py] missing key `{key}`"
        assert py_section[key].strip().lower() == expected.lower(), (
            f"[*.py] {key} = {py_section[key]!r}; expected {expected!r}"
        )
    # AC-3: Makefile MUST use tab indent (POSIX). This is the *only* reason
    # the section exists.
    assert "Makefile" in parser, ".editorconfig must declare [Makefile] section"
    assert parser["Makefile"]["indent_style"].strip().lower() == "tab", (
        f"[Makefile] indent_style = {parser['Makefile']['indent_style']!r}; "
        "expected 'tab' (POSIX requires tab indentation for Makefile recipes)"
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
    for ref in refs:
        assert isinstance(ref, str), (
            f"mkdocs nav contains non-str leaf {ref!r} — flatten contract violated"
        )
    for excluded in EXCLUDED_NAV_DOCS:
        for ref in refs:
            assert excluded not in ref, (
                f"mkdocs nav must NOT reference `{excluded}`; found in `{ref}`"
            )


# ---------- Test 6: AC-9 (SHA-pin every non-local hook rev) ----------


def test_every_non_local_hook_rev_is_sha_pinned() -> None:
    cfg = _load_precommit()
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    repos = cfg["repos"]
    assert isinstance(repos, list)
    for repo in repos:
        if repo.get("repo") == "local":
            continue
        rev = str(repo.get("rev", "") or "")
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
        check=False,
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
        check=False,
    )
    assert result.returncode == 0, (
        f"`mkdocs build --strict` exited {result.returncode}; "
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


# ---------- Test 9: AC-10 (contributing.md replaces the S1-04 placeholder) ----

# The S1-04 placeholder assertion (file present + `TODO(S5-02)` marker) was
# retired by S5-02 when the real contributor docs landed. The replacement
# invariants live in tests/unit/test_project_artifacts.py — sections,
# coverage-ratchet datapoints, ADR-0006 four-extras shape, ADR-0007 amendment
# workflow, the "Probe version bumps" Q2 resolution, and the negative-space
# assertion that `TODO(S5-02)` is gone.


# ---------- Test 10: AC-1 robustness (no duplicate hook ids) ----------


def test_no_duplicate_hook_ids() -> None:
    cfg = _load_precommit()
    repos = cfg["repos"]
    assert isinstance(repos, list)
    seen: dict[str, int] = {}
    for repo in repos:
        for h in repo["hooks"]:
            seen[h["id"]] = seen.get(h["id"], 0) + 1
    dups = {hid: count for hid, count in seen.items() if count > 1}
    assert not dups, f"duplicate hook ids in .pre-commit-config.yaml: {dups}"


# ---------- Test 11: AC-11 (print() scoped via exclude:) ----------


def test_print_rule_excludes_tests_and_scripts() -> None:
    """AC-11: the print( rule must be scoped to skip ^tests/ and ^scripts/."""
    hook = _forbidden_patterns_hook()
    exclude = str(hook.get("exclude") or "")
    assert exclude, (
        "AC-11: forbidden-patterns hook must declare `exclude:` to scope the "
        "print( rule away from tests/ and scripts/. If exclusion is internal to "
        "the entry script, lift it to the hook config so it's auditable."
    )
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
    count = sum(1 for line in this.splitlines() if line.startswith("def test_"))
    assert count >= 11, (
        f"test_precommit_and_docs_config.py must define >= 11 test functions; "
        f"found {count}. AC-8 + the validation report require the 12-test plan."
    )
