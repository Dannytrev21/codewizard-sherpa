# Story S1-04 — Pre-commit hooks + editorconfig + gitignore + mkdocs curated nav

**Step:** Step 1 — Establish project skeleton, tooling, and the `fence` CI job
**Status:** Ready
**Effort:** M
**Depends on:** S1-02
**ADRs honored:** ADR-0008, ADR-0012

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

- [ ] `.pre-commit-config.yaml` exists at the repo root declaring hooks: `ruff` (lint), `ruff-format`, `mypy` (strict on `src/`), `gitleaks`, a local `forbidden-patterns` regex hook, `check-yaml`, `check-toml`, `end-of-file-fixer`, and `trailing-whitespace`.
- [ ] The `forbidden-patterns` hook bans (with one regex per pattern) `print(` (outside `tests/` and `scripts/`), `yaml.load(` without `Loader=`, `shell=True`, `yaml.Dumper` (without `CSafeDumper`/`SafeDumper`), `os.system(`, `os.popen(`, `pickle.loads(`, `eval(`, `exec(` (the function call, not `__main__`), `__import__(`.
- [ ] `.editorconfig` exists at the repo root declaring `indent_style = space`, `indent_size = 4`, `end_of_line = lf`, `charset = utf-8`, `insert_final_newline = true`, `trim_trailing_whitespace = true` for `*.py`; and `indent_style = tab` for `Makefile`.
- [ ] `.gitignore` exists at the repo root with at minimum `.codegenie/`, `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `htmlcov/`, `*.egg-info/`, `dist/`, `build/`, `.venv/`, `.env`, `.DS_Store`, `site/` (mkdocs output).
- [ ] `mkdocs.yml` exists at the repo root with `site_name`, `theme = material`, and a curated `nav` that **excludes** `docs/local.md`, `docs/auto-agent-design.md`, `docs/gemini-auto-agent-design.md`, `docs/context.md`, and `docs/localv2.md` (each excluded file has a `# excluded: see final-design.md §2.2 / §5` comment near the `nav` entry that would have included it, or in a top-of-file `# excluded files:` block).
- [ ] `pre-commit install` succeeds and `pre-commit run --all-files` exits 0 on the current tree.
- [ ] `mkdocs build --strict` exits 0 from the repo root.
- [ ] The TDD plan's red test exists, was committed, and is green.

## Implementation outline

1. Write the red test in `tests/unit/test_precommit_and_docs_config.py` per the TDD plan.
2. Author `.pre-commit-config.yaml` with the hook list (pin each hook by SHA-pinned `rev` for supply-chain stability per `phase-arch-design.md §Testing strategy / CI gates` ("Actions pinned by SHA")).
3. Add the `forbidden-patterns` local hook (entry: a small Python or shell script that `grep -E`-checks the staged diff against the regex list).
4. Author `.editorconfig`, `.gitignore`, and `mkdocs.yml`.
5. Run `pre-commit install` and `pre-commit run --all-files`; fix the *minimal* issues so the existing S1-01..S1-03 tree passes.
6. Run `mkdocs build --strict`; confirm no broken-link or missing-page warnings against the curated `nav`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_precommit_and_docs_config.py`

```python
# tests/unit/test_precommit_and_docs_config.py
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_precommit_config_declares_required_hooks() -> None:
    # arrange: pre-commit config lives at the repo root
    cfg_path = PROJECT_ROOT / ".pre-commit-config.yaml"
    assert cfg_path.is_file(), ".pre-commit-config.yaml must exist"
    cfg = yaml.safe_load(cfg_path.read_text())
    # act: collect every hook id across every repo
    hooks = {h["id"] for repo in cfg["repos"] for h in repo["hooks"]}
    # assert: the contract from High-level-impl §Step 1 — every named hook is present
    required = {"ruff", "ruff-format", "mypy", "gitleaks",
                "forbidden-patterns",
                "check-yaml", "check-toml", "end-of-file-fixer"}
    missing = required - hooks
    assert not missing, f".pre-commit-config.yaml missing hooks: {missing}"


def test_forbidden_patterns_hook_bans_adr_violations() -> None:
    # arrange: the local hook's entry / regex set must cover ADR-0008 and ADR-0012
    cfg = yaml.safe_load((PROJECT_ROOT / ".pre-commit-config.yaml").read_text())
    forbidden = None
    for repo in cfg["repos"]:
        for h in repo["hooks"]:
            if h["id"] == "forbidden-patterns":
                forbidden = h
    assert forbidden is not None, "forbidden-patterns hook missing"
    # act: every required pattern must be in the entry/args/files block or a sibling
    # `entry` script. We check the *config* declares awareness; the script's own
    # behavior is tested by the adversarial tests in tests/adv/ in Steps 2 and 4.
    body = yaml.safe_dump(forbidden)
    for needle in ["shell=True", "yaml.load", "os.system", "os.popen",
                   "pickle.loads", "eval(", "yaml.Dumper"]:
        assert needle in body, \
            f"forbidden-patterns hook does not enumerate `{needle}` (ADR-0008/0012)"


def test_gitignore_lists_codegenie_directory() -> None:
    # arrange: .codegenie/ is the on-disk output namespace per CLAUDE.md
    gi = PROJECT_ROOT / ".gitignore"
    assert gi.is_file(), ".gitignore must exist"
    body = gi.read_text()
    # assert: the project's own dogfood gathers are not committed
    for needle in [".codegenie/", "__pycache__/", ".mypy_cache/",
                   ".ruff_cache/", ".pytest_cache/", "site/", ".venv/"]:
        assert needle in body, f".gitignore missing `{needle}`"


def test_editorconfig_uses_lf_and_4_space_indent_for_python() -> None:
    ec = PROJECT_ROOT / ".editorconfig"
    assert ec.is_file(), ".editorconfig must exist"
    body = ec.read_text()
    assert "[*.py]" in body, ".editorconfig must declare a [*.py] section"
    assert "indent_style = space" in body
    assert "indent_size = 4" in body
    assert "end_of_line = lf" in body
    # Makefile must be tab-indented (POSIX requirement)
    assert "[Makefile]" in body, ".editorconfig must declare a [Makefile] section"


def test_mkdocs_nav_excludes_superseded_design_docs() -> None:
    # arrange: per High-level-impl §Step 1 and phase-arch §Testing strategy,
    # mkdocs build --strict must be green; the only way that holds today is
    # by excluding the docs that don't fit the curated narrative.
    mk = PROJECT_ROOT / "mkdocs.yml"
    assert mk.is_file(), "mkdocs.yml must exist"
    cfg = yaml.safe_load(mk.read_text())
    # act: flatten the nav into a list of referenced doc paths
    def _flatten(items):
        for item in items:
            if isinstance(item, dict):
                for v in item.values():
                    if isinstance(v, list):
                        yield from _flatten(v)
                    else:
                        yield v
            else:
                yield item
    referenced = set(_flatten(cfg.get("nav", [])))
    # assert: the five excluded docs are NOT in the nav (they exist on disk but are not navigable)
    for excluded in ["local.md", "auto-agent-design.md",
                     "gemini-auto-agent-design.md",
                     "context.md", "localv2.md"]:
        for ref in referenced:
            assert excluded not in ref, \
                f"mkdocs nav must NOT reference {excluded}; found in `{ref}`"
```

The test fails initially because none of `.pre-commit-config.yaml`, `.gitignore`, `.editorconfig`, or `mkdocs.yml` exists. Run it, observe the assertion failures, commit the failing test.

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
- **Extending the `forbidden-patterns` regex set with `subprocess.run(..., shell=...)`, `marshal.loads`, `dill.loads`, `__builtins__`, `getattr(..., "__"`** — these are filed as Phase 1 hardening per `phase-arch-design.md §Open questions` Q6.
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
