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
$ make bootstrap   # installs [dev] extras via uv (or pip fallback)
$ make check       # runs lint → typecheck → test → fence
```

`make bootstrap` works with or without `uv` on `$PATH`. See
[`docs/phases/00-bullet-tracer-foundations/stories/S1-03-makefile-bootstrap.md`](docs/phases/00-bullet-tracer-foundations/stories/S1-03-makefile-bootstrap.md)
for the full target list.
