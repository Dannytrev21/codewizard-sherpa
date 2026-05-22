# Explore the project, derive the run command

The goal of this stage: end it knowing the **exact command** to run and
**what its output should contain**. Both are written down — never guess.

## Read order

Read these, in this order, stopping once you can state the run command
and the expected-output shape:

1. **`CLAUDE.md`** (repo root) — the "Common commands" section is the
   imperative surface. It lists the CLI invocations verbatim
   (`python -m codegenie gather ./path`, `codegenie audit verify ...`,
   `codegenie vuln-index refresh ...`).
2. **`Makefile`** — the gate commands (`make check`, `make test`,
   `make fence`). You need these for Stage 6 verification.
3. **`docs/get-started.md`** — the operator-facing run guide, exit-code
   table, and the "What's in `repo-context.yaml`" expectation.
4. **`src/codegenie/cli.py`** — the click command tree. The source of
   truth for subcommands, flags, and documented exit codes. Each
   subcommand's docstring lists its exit codes.
5. **`docs/localv2.md`** — the canonical spec. The probe inventory
   (Layers A–G) and the `RepoContext` schema. This is where "what the
   output *should* contain" is defined.
6. The capability's own code — e.g. for `gather`, the probe modules
   under `src/codegenie/probes/`; for `vuln-index`, `src/codegenie/vuln_index/`.

## Deriving the run command

The CLI has a gotcha worth pinning: **global flags bind before the
subcommand**. `codegenie --no-gitignore gather <path>` is correct;
`codegenie gather <path> --no-gitignore` fails with "No such option".
Read the `@click.group` vs `@cli.command` split in `cli.py` to see which
flags are global.

Always run via the project venv: `.venv/bin/python -m codegenie ...`.
A bare `codegenie` may resolve to nothing or to a stale install.

For `gather`, use `--no-gitignore` so the run is non-interactive (the
`.gitignore` prompt is TTY-only and will otherwise hang or skip).

## The capability catalog

The shipped capabilities as of this skill's writing — confirm against
`codegenie --help` at run time, since the surface grows by phase:

| Capability | Command | Produces | Spec |
|---|---|---|---|
| `gather` | `codegenie --no-gitignore gather <repo>` | `.codegenie/context/repo-context.yaml` + `raw/*.json` + `runs/*.json` | `localv2.md` §probe inventory + `RepoContext` schema |
| `audit verify` | `codegenie audit verify --runs-dir … --cache-dir … --yaml-path …` | exit 0 (clean) / 4 (mismatch) | `cli.py` `audit_verify` docstring |
| `vuln-index refresh` | `codegenie vuln-index refresh --source … --index-path …` | a populated sqlite `vuln-index.sqlite` | Phase 3 `S3-03` story |
| `cache prune` | `codegenie cache prune --cache-dir …` | a `cache_gc_completed` event | `cli.py` `cache_prune` docstring |

## Stating the expected output

Before running anything, write down — concretely — what a correct run
produces. For `gather` that means: the envelope validates, and **each
probe in the registry contributes its slice** with a non-degraded
`confidence` *when the sample app supplies that probe's inputs*. The
phrase "when the sample app supplies that probe's inputs" is load-bearing
— it is the line between a real bug and a sample-app deficiency, and you
cannot draw it without having stated the expectation first.

Produce a short **execution plan** the operator could predict: the exact
command, the sample app it runs against, and the bulleted list of
output checks Stage 4 will make. Only then proceed to run.
