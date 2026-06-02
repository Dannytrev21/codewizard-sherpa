# Get started

A 5-minute path from cloning the repo to running `codegenie gather` against any directory.

## What you'll have at the end

A local Python CLI (`codegenie gather`) that walks any repo, dispatches a set of deterministic probes against it, and writes a structured `RepoContext` artifact to `.codegenie/context/repo-context.yaml`. No LLM is involved anywhere in this pipeline — that's a load-bearing architectural commitment ([ADR-0005](production/adrs/0005-no-llm-in-gather-pipeline.md)). The artifact is reproducible, cacheable, and auditable.

## Prerequisites

| Requirement | Why |
|---|---|
| **Python 3.11+** | Phase-baseline interpreter; uses `typing.assert_never`, `Literal`, structural pattern matching |
| **`git`** | Probes that inspect repo state shell out via the subprocess allowlist |
| **`node`** *(optional)* | Required by Phase 1 Node-ecosystem probes if you're running against a Node repo |
| **`uv`** *(optional but recommended)* | `make bootstrap` prefers it; falls back to `pip` automatically if absent |
| **`pre-commit`** | Local commit-time firewall (ruff / mypy / gitleaks / forbidden-patterns) |

Later phases add more external tools (`semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`, `docker`, `strace`). They're not required for Phase 0/1 usage; the CLI checks `$PATH` at startup and prints clear install errors only if you invoke a probe that needs one.

## Install

```console
$ git clone https://github.com/Dannytrev21/codewizard-sherpa.git
$ cd codewizard-sherpa
$ make bootstrap        # installs [dev] extras via uv (or pip fallback)
$ pre-commit install    # arms the local commit-time firewall
```

`make bootstrap` works with or without `uv` on `$PATH`. The pre-commit hook suite is SHA-pinned in [`.pre-commit-config.yaml`](https://github.com/Dannytrev21/codewizard-sherpa/blob/master/.pre-commit-config.yaml); the `forbidden-patterns` local hook enforces architectural ADRs by regex.

## Verify your install

```console
$ make check            # runs lint → typecheck → test → fence
$ make docs             # builds the curated mkdocs site --strict (this site!)
```

The `check` chain runs in under two minutes on a typical laptop. The `fence` step is load-bearing — it asserts that no LLM SDK (`anthropic`, `openai`, `langgraph`, etc.) is importable from the gather-pipeline runtime closure. If that fails, somebody has smuggled an LLM into a place [ADR-0005](production/adrs/0005-no-llm-in-gather-pipeline.md) forbids.

## Run your first gather

```console
$ python -m codegenie gather ./path/to/some/repo
```

The CLI walks the repo, runs every registered probe whose `applies_to_*` rules match, and writes its output under `.codegenie/` inside that repo:

```
your-repo/
├── .codegenie/
│   ├── context/
│   │   ├── repo-context.yaml        # human-facing schema-validated artifact
│   │   ├── raw/                     # per-probe raw JSON outputs
│   │   │   ├── language_detection.json
│   │   │   ├── node_build_system.json
│   │   │   └── …
│   │   └── runs/                    # per-run audit records (BLAKE3-anchored)
│   │       └── 2026-05-15T13-42-07Z.json
│   └── cache/                       # content-addressed; safe to delete
│       └── …
└── (your existing files)
```

On a TTY, `gather` will prompt before appending `.codegenie/` to your repo's `.gitignore`. Pass `--auto-gitignore` to skip the prompt, or `--no-gitignore` to leave `.gitignore` alone.

## CLI surface

```console
$ python -m codegenie --help
$ python -m codegenie gather <path>      # vertical slice — primary command
$ python -m codegenie audit verify …     # pure-read verifier
$ python -m codegenie cache gc           # Phase-1+ cache cleanup (stub today)
```

| Flag | Effect |
|---|---|
| `--verbose` | Emit DEBUG events to stderr |
| `--version` | Print version + exit |
| `--refresh-tools` | Re-detect external tools on `$PATH` |
| `--auto-gitignore` | Append `.codegenie/` to repo's `.gitignore` without prompting |
| `--no-gitignore` | Never touch `.gitignore` (mutually exclusive with `--auto-gitignore`) |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Gather completed successfully |
| `2` | All probes failed |
| `3` | Schema validation failed (writes `.yaml.invalid` sibling) |
| `4` | `audit verify` mismatch |
| `5` | Output directory is a symlink — refused |
| `6` | Secret-shaped field detected in output — refused |

> **`audit verify` on an empty `--runs-dir` exits `0`.** Verifying an empty
> set of audit anchors is a vacuous pass — there is nothing to mismatch. If
> you point `--runs-dir` at the wrong (but existing) directory, you will get
> a green exit `0` with nothing actually checked. Confirm the run actually
> walked anchors by reading the `audit.verify.ok` summary event's
> `run_records_walked` / `probes_walked` / `yaml_anchors_walked` counters —
> a real verification reports non-zero counts.

## What's actually in `repo-context.yaml`?

Each probe owns a disjoint slice of the schema. After Phase 0 ships `LanguageDetectionProbe`, a small Python repo's artifact looks like:

```yaml
schema_version: "0.2.0"
gathered_at: "2026-05-15T13:42:07Z"
languages:
  python:
    bytes: 12842
    files: 7
    confidence: high
build_system: null      # Phase 1 adds Node detection; Python later
manifests: []           # Phase 1 adds Node lockfile parsing
# … etc; slices are additive, never overwritten
```

The schema grows by **addition** as new probes ship across phases. Existing probe output never changes shape silently — that would defeat the cache and break downstream consumers. See [ADR-0007](production/adrs/0007-probe-contract-preserved-poc-to-service.md) for the contract preservation discipline.

## Where to go next

- **Understanding the architecture** — start with the [Architecture overview](architecture.md), then read the [Production design](production/design.md) for the full Temporal-orchestrated picture
- **Tracking what's built** — the [Roadmap](roadmap.md) lays out all 17 phases; the README has the current implementation status
- **Contributing a probe / phase / story** — see the [Contributing guide](contributing.md)
- **The "why" behind every decision** — every architectural commitment has a numbered [ADR](production/adrs/README.md)

## Troubleshooting

??? question "`make bootstrap` fails with "uv: command not found""
    Bootstrap falls back to `pip` automatically when `uv` is missing — re-run; you should see `python -m pip install -e ".[dev]"`. If that fails too, check your Python version (`python --version`); 3.11+ required.

??? question "`make check` fails on the `fence` step"
    The fence asserts no LLM SDK is importable from `codegenie.cli` or `codegenie/__init__.py`. If you imported `anthropic` / `openai` / `langgraph` / `httpx` / `requests` / `socket` into a gather-pipeline module, the fence will refuse the build. The fix is structural: route through one of the existing chokepoints, or land an ADR that broadens the allowlist explicitly.

??? question "`codegenie gather` exits with code 6 (secret-shaped field rejected)"
    The two-pass sanitizer ([Phase 0 ADR-0008](phases/00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md)) refused to persist what looked like a credential. Inspect the probe output; if the value really is a secret, the probe shouldn't be capturing it. If it's a false positive, the redaction patterns need to grow — open an issue.

??? question "`runtime_trace` / `sbom` / `cve` probes report `unavailable`"
    These three Layer C probes inspect a **built container image**, not just source code, so they have host prerequisites the source-only probes don't:

    - `runtime_trace` builds the repo's `Dockerfile` and traces each scenario under `strace` — **Linux-only**; it needs `docker` and `strace`.
    - `sbom` runs `syft` over the image `runtime_trace` built.
    - `cve` runs `grype` over the SBOM `sbom` produced.

    On macOS `runtime_trace` is `unavailable` **by design** (no `strace`), and that cascades to `sbom` and `cve`. This is honest degradation, not a failure. To exercise the full chain, run the gather on Linux (or in CI) with `docker`, `strace`, `syft`, and `grype` installed.

??? question "`semgrep` ran but reports `skipped` / `config_absent`"
    `semgrep` defaults to the `p/nodejs` registry pack, which is fetched over the network. When that ruleset can't be loaded (offline, registry unreachable), semgrep still exits cleanly having run **zero rules** — the probe reports `outcome: skipped (config_absent)` rather than a misleading clean scan. Point it at a local org ruleset by setting `semgrep_config` in `.codegenie/config.yaml`. Note that a repo-local `.semgrep.yml` is **not** auto-detected — analyzed-repo scanner config is intentionally not trusted.

??? question "Logs include `probe.raw_artifact.missing_on_cache_hit` warnings"
    A cache hit served a probe's `ProbeOutput` from `.codegenie/cache/`, but the probe's staged raw artifact (under `.codegenie/_probe_raw/<name>.json` or `.codegenie/context/<name>.json`) is no longer on disk. Result: `.codegenie/context/raw/<name>.json` is **not** re-materialized this run — the YAML envelope still ships full data, but the raw JSON sidecar is missing. The usual cause is manually deleting `.codegenie/context/` while preserving `.codegenie/cache/`. To force a clean re-materialization, delete the whole `.codegenie/` namespace or run `codegenie cache prune --all` and re-gather.
