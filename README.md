# codewizard-sherpa

Autonomous agentic system that opens PRs to modify code across repos at
portfolio scale. See [`docs/`](docs/) for the design, roadmap, and ADRs.

This repo is currently bootstrapping Phase 0 (the bullet-tracer foundations
described in [`docs/phases/00-bullet-tracer-foundations/`](docs/phases/00-bullet-tracer-foundations/)).
The implementation entry point is the `codegenie` CLI (`src/codegenie/`).

```console
$ python -m codegenie --help
$ python -m codegenie gather ./path/to/repo
```

### Phase 0 subcommand surface

- `codegenie gather <path>` — vertical slice. Walks the repo, dispatches
  the registered probes (Phase 0 ships `LanguageDetectionProbe`), and
  writes `.codegenie/context/repo-context.yaml` + a per-run audit record
  under `.codegenie/context/runs/`. Exit codes: `0` ok, `2` all probes
  failed, `3` schema validation failed (writes `.yaml.invalid` sibling),
  `5` symlink output refused, `6` secret-shaped field rejected.
- `codegenie audit verify --runs-dir <r> --cache-dir <c> --yaml-path <y>`
  — pure-read verifier. Recomputes per-probe blob anchors + the whole-YAML
  anchor; exit `0` clean, exit `4` mismatch.
- `codegenie cache gc` — Phase-1+ stub (logs `cache.gc.stub` and exits 0).

Global flags: `--verbose` (DEBUG events), `--version`, `--refresh-tools`
(re-detect external tools), `--no-gitignore` / `--auto-gitignore`
(skip / auto-append `.codegenie/` to `.gitignore`; mutually exclusive —
combining them exits 2 with a click usage error). On a TTY, `gather`
prompts before appending the canonical two-line block
(`# codewizard-sherpa generated artifacts; safe to delete\n.codegenie/\n`);
on non-TTY (CI), the append is skipped with a structured warning. A
`.gitignore` that already contains a line matching `^\.codegenie/?\s*$`
is detected as idempotent and never rewritten (mtime preserved).

## Quickstart

```console
$ make bootstrap        # installs [dev] extras via uv (or pip fallback)
$ pre-commit install    # arms the local commit-time firewall (S1-04)
$ make check            # runs lint → typecheck → test → fence
$ make docs             # builds the curated mkdocs site (--strict)
```

`make bootstrap` works with or without `uv` on `$PATH`. The pre-commit hook
suite (ruff, ruff-format, mypy, gitleaks, `forbidden-patterns`, check-yaml,
check-toml, end-of-file-fixer, trailing-whitespace) is SHA-pinned and
defined in [`.pre-commit-config.yaml`](.pre-commit-config.yaml); the
`forbidden-patterns` local hook enforces ADR-0008 and ADR-0012 by regex.
See
[`docs/phases/00-bullet-tracer-foundations/stories/S1-03-makefile-bootstrap.md`](docs/phases/00-bullet-tracer-foundations/stories/S1-03-makefile-bootstrap.md)
for the full target list and
[`docs/phases/00-bullet-tracer-foundations/stories/S1-04-precommit-editorconfig-mkdocs.md`](docs/phases/00-bullet-tracer-foundations/stories/S1-04-precommit-editorconfig-mkdocs.md)
for the pre-commit / editorconfig / mkdocs setup.

## CI pipeline

Every PR runs through six SHA-pinned jobs across Python 3.11 / 3.12 ×
`ubuntu-24.04`:

| Job | What it runs | Why it's load-bearing |
|---|---|---|
| `lint` | `make lint` (ruff) + `make lint-imports` (import-linter) | Structural cold-start defense — blocks heavy modules from `codegenie.cli` and `codegenie/__init__.py` |
| `typecheck` | `make typecheck` (mypy `--strict`) | Catches narrowed-type drift early |
| `test` | `pytest -q` (default selection excludes `-m bench` — advisory canaries opt in via the `bench` step) + `bench-collection-guard` (gating, asserts exactly 3 bench tests) + advisory `bench` step (`continue-on-error: true`, uploads `bench-results.json` artifact) | Full suite + advisory perf canaries |
| `security` | `pip-audit` + `osv-scanner` against `uv.lock` | Supply-chain advisories; HIGH/CRITICAL fails the job |
| `docs` | `mkdocs build --strict` (path-filtered on `docs/**` + `mkdocs.yml`) | Docs gate |
| `fence` | `pytest -q tests/unit/test_pyproject_fence.py` after a two-step bare install | **Load-bearing ADR-0002 gate** — refuses any LLM SDK in the gather-pipeline runtime closure |

Workflow files: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (five
jobs), [`.github/workflows/docs.yml`](.github/workflows/docs.yml) (the
sixth, path-filtered separately to honor the ≤90s walltime advisory). All
third-party actions are pinned by 40-character SHA; concurrency is grouped
by `${{ github.ref }}` with `cancel-in-progress: true`. See
[`docs/phases/00-bullet-tracer-foundations/stories/S1-05-ci-fence-import-linter.md`](docs/phases/00-bullet-tracer-foundations/stories/S1-05-ci-fence-import-linter.md)
for the full setup story.
