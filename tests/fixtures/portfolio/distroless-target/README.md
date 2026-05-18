# `distroless-target/` fixture

**Phase-7 forward-looking** — exercises Layer C against an
already-distroless base; primary user is `runtime_trace` + `sbom` +
`cve`. The final-stage `FROM` line is pinned to a sha256 content digest
(S7-01 AC-21b regex `^FROM\s+\S+@sha256:[0-9a-f]{64}\b`) so the image
identity is reproducible and tag drift (`:latest` repushes by upstream
maintainers) cannot silently change probe outputs.

> **The digest is part of the contract.** Re-pinning is a deliberate
> fixture-update PR that regenerates affected goldens — not a silent
> background operation. Use `docker manifest inspect
> gcr.io/distroless/nodejs20-debian12:nonroot` to discover the current
> digest; paste it into the `Dockerfile` `FROM` line and update this
> README's digest note.

The current pin is a sample digest placeholder for fixture purposes;
operators running `regenerate.sh` for real container builds should
re-pin to the live distroless digest first (any 64-hex digest passes
the static shape test, but `docker build` will fail until the pin
resolves on the upstream registry).

## File-by-file — which probes consume what

| Relpath | Consuming probe(s) | Purpose |
|---|---|---|
| `package.json` | `language_detection`, `node_build_system`, `node_manifest` | Minimal Node manifest — no dependencies, single `start` script. |
| `index.js` | `language_detection`, `runtime_trace`, `entrypoint` | 5-line `console.log("ok"); process.exit(0);` body. Executed under `strace` by `runtime_trace` in the already-distroless code path. |
| `Dockerfile` | `dockerfile`, `entrypoint`, `shell_usage`, `certificate`, `runtime_trace`, `sbom`, `cve` | Two-stage build; final stage `FROM gcr.io/distroless/nodejs20-debian12@sha256:...`. **No `USER` directive** — distroless images run as non-root by default (`runtime_trace` records the running UID via `strace`; the no-`USER`-directive invariant is a Phase-7 real-world signal). |
| `README.md` | — | This file. |
| `regenerate.sh` | — | Review-as-code; invokes `docker build` + `docker inspect` (both via the bare `docker` binary in `ALLOWED_BINARIES`); writes the resolved digest to gitignored `built-image.digest`. |
| `.gitignore` | — | `.codegenie/`, `built-image.digest`, and local image tarballs (`*.tar`, `*.tar.gz`). |

## `built-image.digest` content-shape contract (AC-38)

When `regenerate.sh` succeeds, `built-image.digest` (gitignored) is a
single line matching `^sha256:[0-9a-f]{64}\n$`. `ProbeContext.image_digest_resolver`
reads this file via `Path.read_text().strip()` and relies on the
`sha256:` prefix being present. Any future resolver implementation must
preserve the shape; the shape test at
`tests/unit/test_distroless_target_built_image_digest_shape.py`
asserts this (skipped unless the file exists locally or
`CODEGENIE_REGEN_FIXTURES=1`).

## `image_digest_resolver` happy-path smoke (AC-36)

After S5-02 lands, run:

```bash
codegenie gather tests/fixtures/portfolio/distroless-target/
```

Exit 0 + image digest resolved via `ProbeContext.image_digest_resolver`
is the manual smoke. Not a CI assertion (requires docker on the host).

## Forbidden subpaths

The shape test rejects `node_modules/`, `.codegenie/`, `dist/`,
`coverage/`, `build/`, `build/Release/`, `.DS_Store`.

## Maintenance rule

Same as `minimal-ts/` and `native-modules/`: one `_FileSpec` entry per
added file plus a row in the table above.
