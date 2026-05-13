# codewizard-sherpa

Autonomous agentic system that opens PRs to modify code across repos at
portfolio scale. See [`docs/`](docs/) for the design, roadmap, and ADRs.

This repo is currently bootstrapping Phase 0 (the bullet-tracer foundations
described in [`docs/phases/00-bullet-tracer-foundations/`](docs/phases/00-bullet-tracer-foundations/)).
The implementation entry point is the `codegenie` CLI (`src/codegenie/`).

```console
$ python -m codegenie --help
```

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
