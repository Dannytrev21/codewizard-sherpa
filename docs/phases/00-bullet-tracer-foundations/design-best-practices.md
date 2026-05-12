# Phase 0 — Bullet tracer + project foundations

**Lens:** best-practices-first
**Date:** 2026-05-11
**Companions (parallel):** `design-performance.md`, `design-security.md`
**Source of truth for scope:** [`docs/roadmap.md` §"Phase 0"](../../roadmap.md), [`localv2.md` §12 (Week 1)](../../localv2.md), [`CLAUDE.md` "Conventions to follow when writing the POC"](../../../CLAUDE.md)

> **Posture.** This is the "boring tech, predictable not clever, conventions over taste" pass. Phase 0 ships almost no business logic — it ships the *conventions that every subsequent phase will inherit*. Every shortcut taken here becomes a wart in Phases 1–16. The bar is therefore higher than the feature surface suggests.

---

## 1. Phase intent restated in best-practices terms

Phase 0 ships **four artifacts** and nothing else:

1. A runnable `codegenie gather <path>` CLI that exits 0 on a clean repo.
2. A green CI pipeline (lint + type + test) on every PR to `main`.
3. A locally-buildable `mkdocs-material` site over the existing `docs/` tree.
4. Exactly one trivial probe — `LanguageDetectionProbe` — wired through the *real* probe contract from [`localv2.md` §4](../../localv2.md), the *real* coordinator, the *real* cache layer, the *real* schema validator, the *real* output writer.

Success looks like: **a reviewer with no prior context can clone the repo, run `make bootstrap`, run `make check`, and have green output in under five minutes** — and that the resulting harness is the same one Phase 1 will load real Layer A probes into without renaming a single file. The probe contract is the spine of the entire roadmap; Phase 0's job is to plant it correctly.

The work this phase **does not** do (and the temptation to do it is real):

- No real probes beyond `LanguageDetectionProbe`. Layer A in full is Phase 1.
- No `IndexHealthProbe`, no schema for B–G, no fixtures beyond the trivial.
- No async optimization, no benchmark suite, no Redis, no Docker.
- No `pydantic` models for things that don't yet exist.
- No "while we're in here" cleanup. We are establishing, not refactoring.

This is **Rule 2 (Simplicity First)** and **Rule 3 (Surgical Changes)** applied to scaffolding.

---

## 2. Load-bearing conventions locked in this phase

These propagate to every later phase. Get them wrong here and Phase 1+ pays compound interest.

### 2.1 Project layout (`src/` layout, single distribution)

```
codewizard-sherpa/
├── pyproject.toml              # PEP 621 — single source of metadata
├── README.md
├── CLAUDE.md
├── Makefile                    # one-line tasks: bootstrap, check, fmt, test, docs
├── .pre-commit-config.yaml
├── .gitignore
├── .editorconfig
├── mkdocs.yml
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   ├── ISSUE_TEMPLATE/
│   │   ├── new-probe.md
│   │   ├── new-skill.md
│   │   └── adr-amendment.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── CODEOWNERS
├── docs/                       # already exists; mkdocs serves this
├── src/
│   └── codegenie/
│       ├── __init__.py         # exports __version__ only
│       ├── __main__.py         # python -m codegenie
│       ├── cli.py              # click entry point
│       ├── version.py
│       ├── logging.py          # structured logging configuration
│       ├── errors.py           # exception hierarchy (one place)
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py       # ~/.codegenie + repo .codegenie merge
│       │   └── defaults.py
│       ├── probes/
│       │   ├── __init__.py
│       │   ├── base.py         # ABC verbatim from localv2.md §4
│       │   ├── registry.py     # @register_probe + all_probes()
│       │   └── language_detection.py
│       ├── coordinator/
│       │   ├── __init__.py
│       │   ├── coordinator.py  # asyncio dispatch (stub: serial in Phase 0)
│       │   └── snapshot.py     # RepoSnapshot construction
│       ├── cache/
│       │   ├── __init__.py
│       │   ├── store.py        # filesystem-backed; content-addressed
│       │   └── keys.py
│       ├── schema/
│       │   ├── __init__.py
│       │   ├── repo_context.schema.json   # versioned, validated
│       │   └── validator.py
│       └── output/
│           ├── __init__.py
│           ├── writer.py       # repo-context.yaml + raw/
│           └── paths.py        # .codegenie/ path resolution
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_probe_contract.py
│   │   ├── test_registry.py
│   │   ├── test_cache_store.py
│   │   ├── test_schema_validation.py
│   │   └── test_output_writer.py
│   ├── smoke/
│   │   └── test_cli_help_and_empty_dir.py
│   └── fixtures/
│       └── empty_repo/
│           └── .gitkeep
└── docs/phases/00-bullet-tracer-foundations/
    ├── design-best-practices.md   # this file
    ├── design-performance.md
    └── design-security.md
```

**Decisions defended:**

- **`src/` layout, not flat.** Flat-layout (`codegenie/` at repo root) lets `import codegenie` accidentally succeed against the *uninstalled* tree, hiding packaging bugs that only surface in production. `src/` forces every test and every CI run to exercise the installed wheel path. This is the [PyPA-recommended layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) and is non-controversial in 2026.
- **One distribution, one package name.** Phase 0 is not the time for plugin entry points, namespace packages, or a separate `codegenie-core`. If we ever split, we split when the second consumer exists.
- **`__main__.py` exists.** `python -m codegenie gather` must work even before the console script is installed. This is what makes `pipx run --spec . codegenie gather` reliable for reviewers.
- **`errors.py` is one file.** Every later phase will be tempted to define its own exception base. Establish the hierarchy once: `CodegenieError → ConfigError | ProbeError | CacheError | SchemaError`. New phases add subclasses; they do not start their own roots.

### 2.2 Tooling versions and choices

| Concern | Choice | Why |
|---|---|---|
| Python | **3.11+** (CI matrix: 3.11, 3.12) | Roadmap requires 3.11+. PEP 657 fine-grained tracebacks + `tomllib` in stdlib are big wins. 3.12 ships in the matrix from day one because adding it later means fixing test failures in a vacuum. Skip 3.13 until the SDK ecosystem catches up. |
| Packaging build backend | **`hatchling`** | Stdlib-adjacent, no Rust toolchain required to build wheels, owned by PyPA. `setuptools` still works but `hatchling` is the modern default and reads cleaner in `pyproject.toml`. Avoid `poetry` (re-implements dependency resolution; locks us into its workflow) and `pdm` (smaller ecosystem). |
| Environment / install | **`uv`** for dev workflow; `pip` for CI install verification | `uv` is now the fastest Python installer by an order of magnitude and is stable as of 2026. Pin `uv` in CI for reproducibility. Keep a `pip install -e ".[dev]"` path documented for users who refuse to install another tool — it must work. |
| Lock file | **`uv.lock`** at the repo root, committed | Locked dev environment is reproducible. CI installs from the lock; non-lock installs are tested in a separate "loose" job that runs weekly so we catch dependency drift early. |
| Lint | **`ruff`** (lint + format, single tool) | Replaces `flake8`, `isort`, `black`, `pyupgrade`, and twenty plugins with one Rust binary. The roadmap calls for ruff explicitly. Run `ruff check` and `ruff format --check` in CI as separate steps so failures are diagnosable. |
| Type checking | **`mypy --strict`** | Strict from day one. Adding strict later means a hundred-file migration; adding loose now means we never tighten it. Roadmap explicitly says "strict mypy". |
| Test runner | **`pytest`** + `pytest-asyncio` + `pytest-cov` | Standard. `pytest-asyncio` mode is `auto` so async tests don't need decorators. |
| Coverage | **`coverage.py` via `pytest-cov`** | Branch coverage on. Floor: 90% line, 80% branch for `src/codegenie/` (excluding `cli.py` because click test ergonomics aren't worth the gymnastics). The floor is enforced in CI; it goes *up* as phases add code, never down. |
| Pre-commit | **`pre-commit`** with ruff, mypy, end-of-file fixer, trailing whitespace, check-yaml, check-json, check-toml, no-commit-to-main | `mypy` runs in pre-commit *and* CI. Slow but worth it — type errors caught at commit are 10x cheaper than caught in CI. If it's too slow, the answer is "use `pre-commit run --files` per-file" not "drop mypy". |
| Docs | **`mkdocs-material`** + `mkdocs-include-markdown-plugin` | Roadmap mandates mkdocs-material. `mkdocs build --strict` in CI — any broken link, any duplicated heading, any reference to a non-existent page fails the build. |
| ADR format | **Nygard-style markdown**, numbered, frozen | Folder already exists at `docs/production/adrs/`. Phase 0 adds no ADRs; it adds the issue template for amending them. |

Anti-choices worth naming so they don't sneak back:

- **No `tox`.** `nox` would be the modern alternative if we wanted matrix automation, but the CI matrix is short enough that GitHub Actions `strategy.matrix` is simpler.
- **No `black` separately.** `ruff format` covers it.
- **No `pylint`.** `ruff` covers it; running both is double work for the same diagnostics.
- **No `sphinx`.** Reviewers don't read Sphinx for an internal tool. mkdocs renders the existing `docs/` tree as-is.
- **No `pydantic` v1.** Phase 0 doesn't need pydantic at all; the dataclasses from `localv2.md` §4 are sufficient. Pydantic enters in Phase 6 (state ledger).

### 2.3 The probe contract: copy-paste verbatim, then freeze

This is the most important convention in Phase 0. `src/codegenie/probes/base.py` is **the exact ABC from [`localv2.md` §4](../../localv2.md)** — same field names, same types, same default values, same docstrings.

**Why no improvements yet:** the contract is the seam between the local POC and the eventual service ([`localv2.md` §4](../../localv2.md), [`design.md` §6](../../production/design.md#poc-to-service-mapping)). The roadmap explicitly says probes lift from POC to service unchanged. Any "small improvement" in Phase 0 — renaming `schema_slice` to `slice`, hoisting `confidence` to an enum, splitting `ProbeOutput` into success/failure variants — is a future merge conflict with the service team. The right time to evolve the contract is when both the POC and the service have shipped enough probes to know what hurts.

**Concrete rules:**

- `Probe` is an `abc.ABC`. Concrete probes override only `run` (and optionally `applies` / `cache_key`).
- Class attributes (`name`, `layer`, `tier`, `applies_to_*`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy`) are typed and have sensible defaults where the contract allows. Subclasses set them as class-level assignments — no `__init_subclass__` magic.
- Registration is **decorator-only** (`@register_probe` from `localv2.md` §4). There is no central `PROBES = [...]` list anywhere. Adding a probe in Phase 1 is one file: `src/codegenie/probes/<name>.py` with the decorator. This is the "extension by addition" invariant ([`design.md` §2.5](../../production/design.md#2-load-bearing-architectural-commitments)) implemented as a Python pattern.
- The registry is **importable but not auto-populated**. Test code that wants the registry pristine creates a fresh registry instance; global mutable state is a test hazard. Phase 0 ships a `Registry` class plus a module-level default instance, so tests can pass `Registry()` instead of monkeypatching.
- **No probe inheritance hierarchies.** If two probes share helpers, they share a *function* in `probes/_helpers/`, not a `BaseNodeProbe` parent class. Composition over inheritance is non-negotiable here — inheritance hierarchies in plugin systems are how you get diamond problems in Phase 7 (`CLAUDE.md` Rule 2, Rule 11).

### 2.4 Configuration loading: explicit, layered, total

`localv2.md` §13 defines three config sources: `~/.codegenie/config.yaml`, repo `.codegenie/config.yaml`, CLI flags. Phase 0 implements all three, even though `LanguageDetectionProbe` consumes none of them, because the merge precedence is a load-bearing convention.

```
defaults  <  ~/.codegenie/config.yaml  <  $repo/.codegenie/config.yaml  <  CLI flags
```

Implementation:

- `config/defaults.py` — typed dataclass with every field present and sane defaults. This is the only place defaults live.
- `config/loader.py` — `load_config(repo_root: Path, cli_overrides: dict) -> Config` returns the merged, validated object. Source of every field is tracked (a `Provenance` enum) and logged at startup. **Fail-loud rule:** if the user sets a key that doesn't exist in defaults, the CLI errors out with `Unknown config key: foo.bar (typo? did you mean foo.baz?)`. Silent ignore is the worst UX.
- YAML parsing uses **`yaml.safe_load`** — never `yaml.load`. Phase 0 establishes the lint rule (`ruff` rule `S506`) that bans `yaml.load` repo-wide. The security subagent will second this.

### 2.5 Logging: structured from byte one

Reviewers will not read unstructured logs once Phase 5+ ships traces. Establish the format now.

- **`structlog`** as the logging library. Adds ~1 dep but pays back immediately: every log line is JSON in CI, pretty-printed in TTY.
- One logger config in `logging.py`, called once from `cli.py`'s entry. No `logging.getLogger(__name__)` ceremony elsewhere — accept `logger` as a parameter or pull from `structlog.get_logger()`.
- Log levels: `INFO` is the default user-visible band; `DEBUG` only with `--verbose`. **No `print()` anywhere in `src/`** — `ruff` rule `T201` enforces.
- Probe runs emit one structured event per lifecycle stage: `probe.start`, `probe.cache_hit`, `probe.skip`, `probe.success`, `probe.failure`. These are the same event names Phase 6 will hook into for the state ledger; defining them now means Phase 6 doesn't have to rename them.

### 2.6 Error model: one hierarchy, each level meaningful

```python
# src/codegenie/errors.py
class CodegenieError(Exception): ...
class ConfigError(CodegenieError): ...      # bad config file, unknown key, etc.
class ToolMissingError(CodegenieError): ... # external CLI not on PATH
class ProbeError(CodegenieError): ...
class ProbeTimeoutError(ProbeError): ...
class CacheError(CodegenieError): ...
class SchemaValidationError(CodegenieError): ...
```

Rules:

- **One root for all our errors.** `except CodegenieError` in `cli.py` is the only place we render user-facing messages; everywhere else lets exceptions propagate.
- **No bare `except:`** ever. `ruff` rule `E722`. Catching `Exception` requires a comment.
- Exceptions carry data, not just messages: `ToolMissingError("scip-typescript", install_hint="npm install -g @sourcegraph/scip-typescript")`. The renderer in `cli.py` formats it.

### 2.7 Output: machine first, human second, both validated

- **YAML** for `.codegenie/context/repo-context.yaml` (the human-facing artifact) — matches `localv2.md` §3.2.
- **JSON** for everything under `.codegenie/context/raw/` — faster to parse, no ambiguity about types.
- The writer **always validates against the JSON Schema** before writing. The schema lives at `src/codegenie/schema/repo_context.schema.json` and ships in the wheel as package data.
- **`schema-version.txt`** is written next to the YAML on every gather. Phase 1+ adds compatibility checks; Phase 0 just establishes the convention.

The Phase 0 schema is minimal but complete *for what Phase 0 produces*:

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://codewizard-sherpa.dev/schemas/repo-context/v0.1.0.json",
  "type": "object",
  "required": ["schema_version", "generated_at", "repo", "probes"],
  "properties": {
    "schema_version": { "const": "0.1.0" },
    "generated_at": { "type": "string", "format": "date-time" },
    "repo": {
      "type": "object",
      "required": ["root", "git_commit"],
      "properties": {
        "root": { "type": "string" },
        "git_commit": { "type": ["string", "null"] }
      }
    },
    "probes": { "type": "object", "additionalProperties": true }
  },
  "additionalProperties": false
}
```

`additionalProperties: false` at the root and on every fixed object is the right default. Probe slices under `probes.*` are `additionalProperties: true` until Phase 1 fixes their shape — but the per-probe schemas land *with their probes*, not in this central file. The central schema knows the envelope; probes own their slices.

---

## 3. The one real probe: `LanguageDetectionProbe`

The whole point of Phase 0 is that the harness ends-to-ends through one probe. The probe must be *trivial enough to be obviously correct* and *real enough to exercise every seam*.

### 3.1 Behavior

Given a repo root, count files by extension and emit a `{language: file_count}` map. Languages recognized in Phase 0:

- `javascript`: `.js`, `.mjs`, `.cjs`
- `typescript`: `.ts`, `.tsx` (excluding `.d.ts`)
- `python`: `.py`
- `go`: `.go`
- `rust`: `.rs`
- `dockerfile`: `Dockerfile`, `Dockerfile.*`, `*.dockerfile`

Anything else is `other`. No tree-sitter, no `linguist`, no heuristic on shebangs. Phase 1's `LanguageDetection` may replace this with something smarter; the Phase 0 version exists to prove the wiring.

### 3.2 Why this probe and not something else

- **No external tool dependencies.** Calling `scip-typescript` or `syft` from Phase 0 forces CI to install them, which is a Phase 1+ concern. The bootstrap path must be `pip install -e ".[dev]" && pytest`.
- **Deterministic without any complications.** Same files in, same counts out. No timezone, no git history, no network.
- **Exercises every seam.** Reads files (declared inputs), produces a schema slice (output writer), runs in <100ms (timeout path is exercised by a unit test with `timeout_seconds=0`, not by this probe naturally), caches by content (the cache key is the SHA-256 of sorted file paths + sizes).
- **Test cases are obvious.** Empty dir → all zeros. JS-only dir → 1 in `javascript`, 0 elsewhere. Mixed dir → matches the count.

### 3.3 Contract conformance

```python
@register_probe
class LanguageDetectionProbe(Probe):
    name = "language_detection"
    layer = "A"
    tier = "base"
    applies_to_tasks = ["*"]
    applies_to_languages = ["*"]
    requires: list[str] = []
    declared_inputs = ["**/*"]   # broad in Phase 0; Phase 1 narrows by extension
    timeout_seconds = 30
    cache_strategy = "content"
```

Note: `declared_inputs = ["**/*"]` is correct for Phase 0 because the probe scans the entire tree. The performance subagent may push back on this — but their fix belongs in Phase 1 alongside the real probe. Phase 0 ships the simplest correct thing.

---

## 4. Test pyramid for Phase 0

The pyramid is short because the surface is small. Make every test earn its keep — **Rule 9 (Tests verify intent, not just behavior)**.

### 4.1 Unit tests (`tests/unit/`)

| Test file | What it asserts | Why it matters |
|---|---|---|
| `test_probe_contract.py` | A class that subclasses `Probe` without overriding `run` cannot be instantiated. A class with all required attrs *can*. The contract's `applies()` defaults to `True`. | Phase 1+ adds probes; the moment someone forgets `run`, this fails before they push. |
| `test_registry.py` | `@register_probe` adds to the registry exactly once even if the module is re-imported. A fresh `Registry()` instance is empty. Duplicate `name` registration raises. | The registry is shared mutable state. If duplicate registration silently overwrites, Phase 7 (extension by addition) breaks in a way that's invisible until production. |
| `test_cache_store.py` | Same `cache_key` → same payload returned. Different inputs → different keys. Corrupt cache entry → re-runs the probe and logs a warning, never crashes. Cache write is atomic (write to tempfile + rename). | Atomicity is what keeps the cache trustworthy across crashes; non-atomic writes leak half-files that make later runs fail mysteriously. |
| `test_schema_validation.py` | Valid envelope passes. Envelope missing `schema_version` fails with a useful error. `additionalProperties` enforcement at root rejects unknown keys. | The schema is the *only* contract between the writer and downstream consumers. If validation is loose, drift is silent. **Rule 12 (Fail loud).** |
| `test_output_writer.py` | Writer creates `.codegenie/context/` if missing. Writes `repo-context.yaml`, `schema-version.txt`, and an empty `raw/` directory. Re-running overwrites cleanly (no merged stale data). | The on-disk layout is a contract with humans reading the artifact — Phase 0 owns the convention. |

### 4.2 Smoke tests (`tests/smoke/`)

One test, `test_cli_help_and_empty_dir.py`:

- `codegenie gather --help` exits 0 and mentions `gather`, `--verbose`, and the path argument.
- `codegenie gather <empty_dir>` exits 0, writes `<empty_dir>/.codegenie/context/repo-context.yaml`, and the YAML validates against the schema.
- Re-running over the same `<empty_dir>` hits the cache (assert via log capture: at least one `probe.cache_hit` event).

This is the **bullet tracer**. If it passes, the harness works end-to-end. If it fails, no other test matters.

### 4.3 Tests **not** to write in Phase 0

- No integration tests against real Node.js repos. That's Phase 1.
- No golden-file tests. Phase 2 owns golden-file infrastructure (per roadmap).
- No property tests, no fuzz tests, no benchmark tests. Add when there's logic worth fuzzing.
- No CLI tests for flags that don't exist yet (`--task`, `--language`, `--cache-clear`). Skeleton flags are scope creep.

### 4.4 Coverage policy

- **Floor:** 90% line, 80% branch on `src/codegenie/` excluding `cli.py`.
- **`cli.py` is exempt from the line floor** because click's argument-parsing branches are tested in the smoke test by behavior, not by counting branches. Coverage games are worse than honest gaps.
- The floor is enforced in CI via `--cov-fail-under=90`. The floor goes up by 1–2 points per phase as more code lands.
- **No `# pragma: no cover` except for `if TYPE_CHECKING:` blocks and `raise NotImplementedError` in ABCs.** Other uses require a code-review comment explaining.

---

## 5. CI pipeline

Single file: `.github/workflows/ci.yml`. One job, four steps, fail-fast across the matrix.

```
matrix: { python-version: ["3.11", "3.12"], os: [ubuntu-24.04] }
steps:
  1. setup-uv (pin uv version)
  2. uv sync --locked  (install from uv.lock)
  3. ruff check . && ruff format --check .
  4. mypy --strict src/ tests/
  5. pytest -q --cov=src/codegenie --cov-branch --cov-fail-under=90
  6. mkdocs build --strict
```

A separate weekly job runs `uv lock --upgrade` + the full suite against `pip install -e ".[dev]"` (no lock) to surface dependency drift early.

**Decisions:**

- **No macOS or Windows runners in Phase 0.** All target users gather on Linux per `localv2.md`. Adding Mac later is one matrix entry. Adding it now without a real consumer is premature.
- **`mkdocs build --strict`** is a CI step. A docs site that builds locally but breaks on PR is the worst class of merge-time bug.
- **Concurrency group** on `${{ github.ref }}` so a fresh push cancels the in-flight job for the same branch. Saves minutes; doesn't risk skipping anything that matters.
- **`actions/cache`** keyed on `uv.lock` for the `.venv/` directory. Cold CI runs in ~2 minutes; warm in ~30 seconds.
- **Permissions: `contents: read` at workflow level**, with finer grants only where needed. The security subagent will second this; calling it out here so they don't have to relitigate.

A failed CI run must be diagnosable from the log without checkout. Each step prints what it ran. No "one giant shell script" steps.

---

## 6. Developer experience: `make`-first, scriptless

A `Makefile` at the repo root with **eight targets, no more**:

```
make bootstrap   # uv sync; pre-commit install
make check       # ruff + mypy + pytest + mkdocs --strict (mirrors CI exactly)
make fmt         # ruff format
make lint        # ruff check (no format)
make types       # mypy --strict
make test        # pytest
make docs        # mkdocs serve
make clean       # rm -rf .venv .pytest_cache .mypy_cache .ruff_cache site
```

Rules:

- **Targets that exist in Makefile must mirror CI exactly.** If a contributor's local `make check` passes, CI passes. Drift between them is a P0 bug.
- **No `scripts/` directory.** Every shell snippet someone wants to write goes in the Makefile, where it's discoverable via `make help`. Random `.sh` files in `scripts/` rot.
- **No `.envrc` or direnv assumptions.** `make bootstrap` produces a working `.venv/`; activation is the contributor's responsibility, documented in README.

---

## 7. Documentation that lands in Phase 0

`docs/` already exists and is the home of the design docs. Phase 0 adds the *minimal* additions to support new contributors:

1. **`docs/README.md`** — table-of-contents over the existing docs, mirrors the reading order from `CLAUDE.md`. Already exists; verify it renders cleanly under mkdocs.
2. **`mkdocs.yml`** — navigation tree, theme config, strict mode on, no plugins beyond `material` and `include-markdown`.
3. **`docs/contributing.md`** — *new*, ~one page. Covers `make bootstrap`, `make check`, branching, PR template, where ADRs live. **Not** a guide to writing probes (that lands in Phase 1 when probes are real).
4. **`docs/phases/`** index — links each phase folder. This file plus the two companions are the first entries.

**Anti-additions:** no `CHANGELOG.md` yet (no release), no `CODE_OF_CONDUCT.md` until there are contributors who aren't the founding team, no `ARCHITECTURE.md` (the production design docs *are* the architecture doc — duplicating is how prose drifts).

---

## 8. The biggest best-practices traps in Phase 0 (and how this design avoids them)

| Trap | Why it matters | This design's countermeasure |
|---|---|---|
| Defining the probe contract slightly differently from `localv2.md` §4 | Service team and POC team diverge silently; Phase 9 lift breaks | `base.py` is copy-pasted verbatim; a test asserts class attribute names and types against a frozen snapshot |
| Adding pydantic / attrs because "we'll need it" | More machinery before there's load to support | `dataclasses` only. Pydantic enters in Phase 6 (state ledger) per roadmap |
| Speculative async optimization | Phase 0 has one probe; concurrency is moot | Coordinator runs serially in Phase 0; the async dispatch lands in Phase 1 with the bounded worker pool. Avoid `asyncio.gather` in `cli.py` |
| Silent config-key typos | Users edit YAML, get no feedback, debug for an hour | Unknown keys are a hard error with a "did you mean?" suggestion (Levenshtein on field names) |
| Schema validation as advisory | Drift creeps in across phases | Validation is in the write path; writer raises `SchemaValidationError` on mismatch. Tests assert |
| Generated artifacts checked into git | `.codegenie/` polluting reviews | `.gitignore` includes `.codegenie/` at root; first-run UX offers to add it to the *target repo's* `.gitignore` (CLAUDE.md convention) |
| `mypy --strict` partially applied | The "we'll tighten it later" promise never happens | Strict from day one across `src/` and `tests/`. The bar is harder to ratchet down than up |
| One-line `Dockerfile` for CI runtime | Establishes Docker as a Phase 0 dep that won't be used until Phase 5 | No Dockerfile in Phase 0. CI runs on `ubuntu-24.04` directly |
| `__init__.py` re-exporting half the package | Import cycles in Phase 3+ | `__init__.py` only exports `__version__`. Callers import from submodules explicitly |
| README rot | New contributor hits commands that no longer work | README's "quickstart" block is *verbatim copy-pasted from* what CI runs. Drift is caught by a test that diffs them |

---

## 9. Risks specific to the best-practices lens

1. **Over-engineering the scaffolding.** The biggest risk is treating Phase 0 like a project rather than a stub. Every additional file in `src/` is a future maintenance burden. The design above is already on the *high* end of what's defensible; if anyone wants to add a subsystem ("a plugin loader", "a config schema generator"), the answer is "Phase 1 or later". **Mitigation:** the file list in §2.1 is the ceiling, not a floor.
2. **Premature consistency.** Forcing a convention that hasn't been pressure-tested. Example: insisting all probes return `confidence: "high"` until proven otherwise. **Mitigation:** call out conventions that are *aspirational* (likely to bend in Phase 1) vs. *load-bearing* (will not bend). The contract from `localv2.md` §4 is load-bearing. Probe slice schemas are aspirational.
3. **Tooling sprawl.** Adding ruff, mypy, pytest, pytest-cov, pytest-asyncio, pre-commit, mkdocs, structlog already crosses ten dev dependencies. **Mitigation:** every dep gets justified in §2.2. New deps in later phases need an ADR amendment.
4. **CI green ≠ correct.** `pytest` passing on a single trivial probe says almost nothing about real behavior. **Mitigation:** the smoke test asserts *behavior the user actually observes* (file on disk, exit code, log content). Phase 1's integration test against a real repo is the next gate.
5. **"Conformance > taste" wears off.** Six months in, someone wants to introduce `attrs` because they prefer it. **Mitigation:** `CLAUDE.md` Rule 11 is in the repo. Phase 0's conventions section in this doc is the reference any future PR review can point to.

---

## 10. Exit criteria (Phase 0 done means)

Reproducing the roadmap criteria with best-practices specifics added:

1. **CLI runs.** `codegenie gather <path>` exits 0 on an empty dir, a Node-only repo, and a polyglot repo. Help text mentions every flag that exists. Unknown flags exit non-zero with a usage hint.
2. **External-tool readiness check.** On startup, the CLI logs which optional tools are present on `$PATH` (Phase 0 has zero required external tools, but the convention is in place — Phase 1's first probe with a tool dep slots into the existing check).
3. **`LanguageDetectionProbe` executes end-to-end.** Reads files, returns a schema slice, slice merges into the envelope, envelope validates, YAML lands on disk, raw artifact (a JSON dump of the count map) lands under `.codegenie/context/raw/language_detection.json`.
4. **Cache works.** Second run on unchanged input emits `probe.cache_hit` for `language_detection` and *does not* read the filesystem again (verified by a `pytest` test that monkeypatches the file walker).
5. **CI is green on `main`.** Lint, type, test, and docs-build all pass on Python 3.11 and 3.12.
6. **Docs site builds locally** with zero warnings via `make docs` and via `mkdocs build --strict` in CI.
7. **Pre-commit hooks installed** by `make bootstrap`, and a commit with a lint violation is blocked before push.
8. **Coverage ≥ 90% line / 80% branch** on `src/codegenie/` excluding `cli.py`.
9. **Issue templates render** in the GitHub UI: new-probe, new-skill, ADR-amendment.
10. **The probe ABC matches `localv2.md` §4 byte-for-byte** — verified by a test that snapshots the class signature.

---

## 11. Handoff to Phases 1+

When Phase 1 starts, this is what it inherits and is *not allowed to change without an ADR amendment*:

- `Probe` ABC in `src/codegenie/probes/base.py`.
- `@register_probe` decorator and the `Registry` shape in `src/codegenie/probes/registry.py`.
- The `.codegenie/` on-disk layout from `localv2.md` §3.2.
- The JSON Schema envelope at `src/codegenie/schema/repo_context.schema.json`.
- Config merge precedence (defaults < user-global < repo < CLI flags) and the fail-loud-on-unknown-keys behavior.
- The error hierarchy in `src/codegenie/errors.py`.
- The Makefile target names (`bootstrap`, `check`, `fmt`, `lint`, `types`, `test`, `docs`, `clean`).
- The CI matrix (Python 3.11 + 3.12, ubuntu-24.04).
- The strict-mypy bar and the coverage floor.

What Phase 1 is *expected* to extend, by addition only:

- New probes in `src/codegenie/probes/<name>.py` with `@register_probe`.
- Per-probe schema fragments under `src/codegenie/schema/probes/<name>.schema.json`, composed into the envelope by reference, not by editing.
- The bounded async dispatch in the coordinator (replacing Phase 0's serial path).
- Fixture repos under `tests/fixtures/` for golden-file and integration testing.
- New external-tool checks in the startup readiness scan.

If any of those "load-bearing" items in §11.1 needs to change in Phase 1, that's a design escape, not a refactor — and it goes through an ADR. **Rule 7 (Surface conflicts, don't average them).**

---

## 12. Open questions to flag (not blocking Phase 0 exit)

These are best-practices judgment calls where the answer is defensibly either way; surfacing them so they don't get decided by default in a PR.

1. **`uv` as a hard requirement or optional accelerator?** The design above pins `uv` in CI but documents the `pip` path. If `uv` becomes a dep we *require* contributors to install, the bootstrap UX is better but the floor is higher. Recommendation: keep both paths working in Phase 0; revisit in Phase 2 once we know how often contributors hit the slow path.
2. **GitHub Actions vs. CircleCI / Buildkite?** Roadmap says GHA. Phase 0 commits to GHA. Worth an ADR before Phase 11 (PR creation at scale) confirms it.
3. **Should the smoke test live in `tests/smoke/` or `tests/e2e/`?** Phase 0 has only one, and the line between "smoke" and "e2e" is fuzzy. Recommendation: `tests/smoke/` now, rename to `tests/e2e/` when there are 3+ such tests and the distinction matters.
4. **`structlog` or stdlib `logging` with a JSON formatter?** stdlib has gotten better. The design above picks `structlog` because the API is materially cleaner and the dep weight is trivial. Worth revisiting only if `structlog` shows up in a security advisory.

These are not "we'll decide later" — they're "we have an answer, it's defensible, write it down so the next contributor doesn't relitigate it".

---

## Appendix A — `pyproject.toml` skeleton (illustrative)

```toml
[project]
name = "codewizard-sherpa"
version = "0.0.1"
description = "Deterministic context gathering for autonomous code-modification agents."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Proprietary" }
dependencies = [
  "click>=8.1",
  "pyyaml>=6.0",
  "jsonschema>=4.21",
  "structlog>=24.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "pytest-cov>=5.0",
  "mypy>=1.10",
  "ruff>=0.5",
  "pre-commit>=3.7",
  "mkdocs-material>=9.5",
  "mkdocs-include-markdown-plugin>=6.2",
]

[project.scripts]
codegenie = "codegenie.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "S", "T20", "RUF", "SIM", "UP"]
ignore = ["S101"]  # asserts allowed in tests

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S"]

[tool.mypy]
strict = true
python_version = "3.11"
files = ["src", "tests"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-ra --strict-markers --strict-config"
testpaths = ["tests"]

[tool.coverage.run]
branch = true
source = ["src/codegenie"]
omit = ["src/codegenie/cli.py"]

[tool.coverage.report]
fail_under = 90
show_missing = true
```

This is the file. Future phases edit it surgically — add a dep, bump a floor — they do not restructure it.
