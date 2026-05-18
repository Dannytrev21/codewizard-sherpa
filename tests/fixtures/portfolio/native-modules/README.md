# `native-modules/` fixture

Covers the **C-extension manifest edge case** Phase 1 deliberately
deferred (`localv2.md` §5.1 native-module catalog). The chosen
dependency is `bcrypt@5.1.0` — manifest format has been stable for
years; declares an `install` script invoking `node-gyp rebuild`; ships
the `binding.gyp` marker `NodeReflectionProbe` (Phase 2 S4-06) detects.

> **No compilation occurs at regen time** — the rationale is **CI
> determinism**: `node-gyp` outputs differ across platforms (Linux
> vs. macOS, glibc vs. musl, gcc vs. clang) and across `node-gyp`
> versions, so any committed `build/Release/*.node` blob would either
> dirty the closed-set test or force per-platform fixture variants.
> Both are worse than the hand-authored-lockfile pattern.

The fixture ships pre-resolved `pnpm-lock.yaml` bytes (Phase-1
`node_typescript_helm/` precedent — `pnpm` is **not** in
`ALLOWED_BINARIES` per 02-ADR-0001). `.npmrc` carries
`ignore-scripts=true` as defense-in-depth for any operator who later
runs `pnpm install` / `npm install` locally; `regenerate.sh` asserts
`build/Release/` is absent on every invocation as the stale-output
check (S7-01 AC-16b).

## File-by-file — which probes consume what

| Relpath | Consuming probe(s) | Purpose |
|---|---|---|
| `package.json` | `language_detection`, `node_build_system`, `node_manifest`, `node_reflection` | Declares the `bcrypt` C-extension dependency and the `install` script invoking `node-gyp rebuild`. The script-trigger marker is what `node_manifest` and `node_reflection` detect. |
| `pnpm-lock.yaml` | `node_build_system`, `node_manifest`, `dep_graph` | Hand-authored lockfile pinning `bcrypt@5.1.0` at exact version. **Bytes are part of the contract** — never regenerated via `pnpm install`. |
| `binding.gyp` | `node_reflection`, `generated_code` | Pure RFC-8259 JSON body (S7-01 AC-13). No Python-style comments, no trailing commas. `node-gyp`'s permissive grammar is out-of-scope; the strict-JSON shape is the load-bearing parser contract. |
| `src/addon.cc` | `language_detection`, `generated_code` | Trivial C++ source. **Never compiled at regen time** — see CI-determinism rationale above. |
| `.npmrc` | `node_manifest` | Single line `ignore-scripts=true`. Defense-in-depth for the operator who runs `pnpm install` locally. |
| `README.md` | — | This file. |
| `regenerate.sh` | — | Review-as-code; idempotent skeleton-verify; AC-16b stale-`build/Release/` check. No package-manager invocation. |
| `.gitignore` | — | `.codegenie/` and `build/` — the latter belt-and-suspenders alongside the stale-output check. |

## Forbidden subpaths

The shape test rejects any of `node_modules/`, `.codegenie/`, `dist/`,
`coverage/`, `build/`, `build/Release/`, `.DS_Store`.

## Maintenance rule

Same as `minimal-ts/`: one `_FileSpec` entry per added file plus a row
in the table above. AC-29 enforces the README/spec round-trip.
