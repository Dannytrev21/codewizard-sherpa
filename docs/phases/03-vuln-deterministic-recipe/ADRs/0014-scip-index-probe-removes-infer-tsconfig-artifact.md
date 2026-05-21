# ADR-0014: `ScipIndexProbe` removes the `scip-typescript --infer-tsconfig` artifact (amends Phase 2 S4-03)

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** probe-discipline · gather-read-only · kernel-amendment · test-hygiene
**Related:** [Phase 2 S4-03 — `ScipIndexProbe`](../../02-context-gather-layers-b-g/stories/), [Phase 2 ADR-0006 — index-freshness sum type](../../02-context-gather-layers-b-g/ADRs/), `tests/fence/test_kernel_frozen.py`, `tests/fence/_phase2_baseline.txt`

## Context

`ScipIndexProbe` (Phase 2, S4-03 — `src/codegenie/probes/layer_b/scip_index.py`) shells out to `scip-typescript index --cwd <repo> --output <blob> --infer-tsconfig`. The `--infer-tsconfig` flag is load-bearing: `scip-typescript` needs a TypeScript project file to index against, and many real repositories (and two portfolio fixtures — `distroless-target`, `native-modules`) ship none. With the flag, `scip-typescript` infers a minimal `tsconfig.json`, **writes it into the `--cwd` directory** (the analyzed repo root), indexes against it — and never removes it.

That leftover file violates a load-bearing architectural commitment: **`gather` is read-only on the analyzed repo except for the `.codegenie/` output namespace.** Three concrete failures follow:

1. **Product bug.** `codegenie gather ./any-repo` against a repo with no `tsconfig.json` leaves a stray, untracked `tsconfig.json` behind — `gather` silently mutates the user's working tree.
2. **Test-hygiene bug.** `scripts/regen_golden.py` runs `gather` against the real `tests/fixtures/portfolio/` directories. The stray file lands as an untracked artifact in `distroless-target/` and `native-modules/`, dirtying the repo on every full `pytest` run.
3. **Cross-probe perturbation.** `node_build_system` and `semantic_index_meta` read `tsconfig.json` from the live repo root. The transient file makes those probes report a TypeScript config for fixtures that genuinely have none — a *semantically wrong* observation ("facts, not judgments" — the fact is false).

`src/codegenie/probes/layer_b/scip_index.py` is a frozen Phase-0/1/2 kernel file: `tests/fence/test_kernel_frozen.py` diffs `HEAD` against `tests/fence/_phase2_baseline.txt` and fails any edit outside `_KERNEL_ALLOWLIST`. Fixing the probe therefore requires this ADR plus an allowlist entry — the sanctioned amendment path.

## Options considered

- **Option A — Drop `--infer-tsconfig`.** Removes the side effect, but `scip-typescript` can no longer index any repo lacking a committed `tsconfig.json` — every such repo falls to the `exit_nonzero` failure path and `index_health` loses its SCIP signal. **Pattern:** capability regression.
- **Option B — Record `tsconfig.json` pre-existence before the `scip-typescript` invocation; in a `finally`, delete the file iff the probe created it.** The probe owns the cleanup of its own side effect, on every exit path (success, timeout, non-zero exit). A pre-existing (committed) `tsconfig.json` is never touched. **Pattern:** resource cleanup at the boundary that acquired it.
- **Option C — Leave the probe untouched; clean the stray file up in `scripts/regen_golden.py` after each gather.** Fixes failure (2) only. The product bug (1) remains — every `gather` still mutates user repos — and (3) still bakes a false TypeScript block into the `node_build_system` goldens, because the regen harness can only clean up *after* the whole gather, long after the concurrent probes have read the live repo. **Pattern:** symptom containment, not a fix.

## Decision

Adopt **Option B**, plus a coordinator-ordering amendment. `ScipIndexProbe.run` captures `tsconfig_preexisted = (repo.root / "tsconfig.json").is_file()` before invoking `scip-typescript`, and a `finally` clause removes `repo.root / "tsconfig.json"` iff `not tsconfig_preexisted` and the file now exists. The `finally` covers every exit path of the `run_external_cli` call (success, `ProbeTimeoutError`, `ToolMissingError`, non-zero exit); the `tool_missing` path is a no-op because the tool never ran. The `unlink` is wrapped in `try/except OSError` — a cleanup failure must never crash the probe — mirroring the existing partial-`.scip`-blob cleanup in `_emit_failure_slice`.

The cleanup is necessary but not sufficient while base probes run concurrently: `semantic_index_meta` can still read the transient `tsconfig.json` during the brief window before cleanup. `ScipIndexProbe` therefore registers with `runs_last=True`, hoisting it out of the prelude so tsconfig-reading base probes finish first. The coordinator also strengthens `runs_last` from queue-position metadata into a temporal tail: non-tail rest probes complete before the `runs_last` probes execute in registry order. This keeps `index_health` after `scip_index`, preserving B2's sidecar read.

`src/codegenie/probes/layer_b/scip_index.py` is added to `_KERNEL_ALLOWLIST` in `tests/fence/test_kernel_frozen.py` with an inline `# adr:` reference to this ADR. The probe contract (`base.py`), the coordinator, and every other Phase-2 probe are untouched — this is a localized correctness fix to one probe's imperative shell, not an extension of the contract.

## Tradeoffs

| Gain | Cost |
|---|---|
| `gather` is read-only on the analyzed repo again — only `.codegenie/` is written | One Phase-2 kernel file leaves the frozen set (allowlisted, ADR-referenced) |
| Portfolio golden harness no longer dirties `tests/fixtures/` on a full `pytest` run | A new `finally` clause widens `run()`'s imperative shell by six lines |
| `node_build_system` / `semantic_index_meta` goldens reflect the fixtures' true state (no false TypeScript block) | `scip_index` now runs in the temporal tail, so SCIP indexing starts later than other base metadata probes |
| `--infer-tsconfig` is retained, so SCIP indexing of `tsconfig`-less repos still works | `scip_index.py` must now be regenerated into `_phase2_baseline.txt` if a future re-baseline is taken |

## Pattern fit

Implements **resource cleanup at the acquiring boundary** — the probe that triggers the artifact's creation is the probe that removes it, in a `finally`, deterministically. Preserves **functional core / imperative shell**: the cleanup is impure and lives in `run()`, the only impure method. Honors **facts, not judgments**: with the transient file gone, the tsconfig-reading probes report the analyzed repo's true configuration rather than a `scip-typescript` artifact. The probe contract in `base.py` stays frozen — extension-by-addition is not violated; this is a bug fix to existing behavior, scoped to one probe.

## Consequences

- `src/codegenie/probes/layer_b/scip_index.py` gains a pre-existence capture and a `finally` cleanup clause in `ScipIndexProbe.run`.
- `ScipIndexProbe` registers as `@register_probe(heaviness="heavy", runs_last=True)` so `--infer-tsconfig` cannot perturb concurrent base probes.
- `src/codegenie/coordinator/coordinator.py` dispatches the `runs_last` tail only after non-tail rest probes complete, then executes tail probes in registry order. This keeps `index_health` after `scip_index` even when `max_concurrent_probes > 1`.
- `tests/fence/test_kernel_frozen.py::_KERNEL_ALLOWLIST` gains one entry: `Path("src/codegenie/probes/layer_b/scip_index.py")` with a `# P3-ADR-0014` comment.
- The portfolio `index_health` goldens (`distroless-target`, `minimal-ts`, `monorepo-pnpm`, `stale-scip`) are regenerated: with `scip-typescript` present on `PATH`, `scip_index` succeeds and `index_health` reports `scip: {confidence: high, freshness: fresh}` instead of the `indexer_error` state recorded when the tool was absent. CI installs `scip-typescript` in the `test` and `portfolio` lanes so the goldens are deterministic across CI and developer machines.
- `node_build_system` / `semantic_index_meta` goldens are **unchanged** — cleanup plus scheduling keep the transient file invisible to them, so `distroless-target` / `native-modules` correctly retain `typescript: null`.
- Unit tests in `tests/unit/probes/layer_b/test_scip_index.py` are unaffected: their `repo_root` fixture commits a `tsconfig.json`, so `tsconfig_preexisted` is `True` and the cleanup is a no-op.
- New invariant: a probe that invokes an external tool which writes into the analyzed repo MUST clean up that artifact. `--infer-tsconfig` is the first such case; future tool integrations follow this precedent.

## Reversibility

**High.** The change is six lines plus one allowlist entry. Reverting restores the prior behavior exactly; the allowlist entry would then be removed in the same change. The `--infer-tsconfig` flag itself is untouched, so the reversal carries no capability risk.

## Evidence / sources

- `src/codegenie/probes/layer_b/scip_index.py::_build_scip_argv` — the `--infer-tsconfig` argv this ADR governs
- `src/codegenie/probes/layer_b/scip_index.py::ScipIndexProbe.run` — the `finally` cleanup this ADR adds
- `tests/fence/test_kernel_frozen.py` + `tests/fence/_phase2_baseline.txt` — the kernel-freeze fence this amendment satisfies
- [Phase 2 ADR-0012 — `ALLOWED_BINARIES` amendment](0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md) — the precedent: a Phase-3 ADR amending a frozen Phase-2 kernel file via `_KERNEL_ALLOWLIST`
- `CLAUDE.md §"Load-bearing architectural commitments"` — "`.codegenie/` is the on-disk output namespace inside any analyzed repo"
