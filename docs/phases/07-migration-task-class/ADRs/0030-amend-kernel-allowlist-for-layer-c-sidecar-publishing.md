# ADR-0030: Re-apply the Layer C raw-sidecar publishing fix; amend the kernel-frozen allowlist for eight Layer C/G probe files

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** regression-rescue · fence · kernel-frozen · adr-amendment · layer-c · sidecar-contract · honest-confidence
**Related:** [Phase 3 ADR-0011](../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (the kernel-frozen fence + `_KERNEL_ALLOWLIST` this ADR amends), [Phase 2 ADR-0006](../../02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md) (the `ScannerSkipped.reason` `config_absent` value the semgrep change reuses), [0009](0009-phase-7-byte-edit-allowlist-fence.md) (the Phase 7 byte-edit allowlist fence — forward dependency, see §Consequences), [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) (extension by addition; a genuinely cross-cutting kernel edit uses the sanctioned loud, ADR-gated path)

## Context

The five Layer C marker probes (`entrypoint`, `shell_usage`, `certificate`, `sbom`, `cve`) read upstream evidence from `.codegenie/context/raw/<name>.json` sidecars via `codegenie.probes.layer_b.index_health.read_raw_slices`. That pattern only works if the upstream probe actually *persists* its sidecar. Two producers — `DockerfileProbe` and `RuntimeTraceProbe` — never did: they returned `raw_artifacts=[]` and wrote nothing under `raw/`. The consequence is silent and total — every consumer emitted `confidence: "unavailable"` on **every** gather, on **every** platform. `entrypoint` declares `.codegenie/context/raw/dockerfile.json` as a `declared_input` and finds nothing; `certificate` declares `.codegenie/context/raw/runtime_trace.json` and finds nothing.

This is exactly the failure mode the project's load-bearing commitments call its worst: **honest confidence** — "silent index staleness is the worst failure mode" — and **facts, not judgments**. A probe that always says `unavailable` is not honest; it is dead. The blast radius reaches Phase 7 directly: the distroless-migration task class consumes Layer C container evidence (`DockerfilePolicyGate`, the Dockerfile recipe engines, `RuntimeShellInvocationProbe` blast-radius analysis, `TargetImageContentProbe`) — all of it degrades to `unavailable` while the bug stands.

Commit `5055292` ("fix(probes/layer_c): publish raw sidecars so marker probes see upstream evidence") fixed it. It was reverted by `7f6a009` because it byte-edited **eight Phase 0/1/2 kernel probe files** — `src/codegenie/probes/layer_c/{certificate,cve,dockerfile,entrypoint,runtime_trace,sbom,shell_usage}.py` and `src/codegenie/probes/layer_g/semgrep.py` — without an `_KERNEL_ALLOWLIST` entry. `tests/fence/test_kernel_frozen.py` (the Phase 3 ADR-0011 audit-and-lint fence) diffs a pinned `_phase2_baseline.txt` SHA against `HEAD`; it only sees committed history, so `make check` passed while the change was uncommitted, then CI went red the moment it landed. The revert restored a green `master` and explicitly recorded that "the sidecar-publishing fix is sound and worth redoing — but as a Phase 7 story with a proper ADR amendment widening `_KERNEL_ALLOWLIST`, not as a silent kernel edit."

The kernel-frozen fence is **designed to be extended this way.** Its own failure message reads: "Either add the file to the allowlist (with an `# adr:` comment) via ADR amendment, or revert the change." This ADR is that amendment.

Three structural reasons no existing test caught the original bug — recorded here so the regression guard this ADR mandates is not later deleted as redundant:

1. **Consumer unit tests fabricate their own upstream.** Each consumer's unit test writes `raw/<name>.json` by hand before running the probe. The producer↔consumer seam was never exercised as a pair.
2. **The portfolio golden test snapshotted the broken output.** It runs a full gather, but its committed goldens recorded the broken `confidence: "unavailable"` slice as the expected baseline. A golden detects *drift*, not *wrongness* — a broken baseline passes forever.
3. **The smoke fixtures have no Dockerfile.** No smoke fixture lets a Layer C container probe produce real output, and the structural smoke check treats `skipped` / empty slices as first-class — it catches *exceptions*, not *silent emptiness*.

## Options considered

- **Option A — Leave the bug unfixed (WONTFIX).** **Pattern:** none. **Rejected** — silent `unavailable` on every gather is the precise "honest confidence" violation the project forbids; it also blocks the Phase 7 migration task class from ever seeing real Layer C evidence.
- **Option B — Re-land commit `5055292` as-is.** **Pattern:** silent kernel edit. **Rejected** — this is what `7f6a009` reverted. It re-breaks `test_kernel_frozen.py` and violates the no-silent-kernel-edit discipline ([production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md)).
- **Option C — Publish the sidecars from new (Phase 7-owned) wrapper probes, leaving the eight kernel files byte-identical.** **Pattern:** wrapper / shadow probe. **Rejected** — a sidecar must be written by the producing probe's own `run()` exit paths (`DockerfileProbe.run`, `RuntimeTraceProbe`'s `_finalize()` chokepoint). A wrapper would re-parse the Dockerfile and re-resolve the image digest, duplicating work and lying to the coordinator's concurrency budget (02-ADR-0003 forbids hidden parallelism / hidden work). It cannot make a *consumer* see `runs_last` ordering either. The fix is intrinsically an edit to the producing probes.
- **Option D — Re-apply `5055292` verbatim and widen `_KERNEL_ALLOWLIST` with the eight touched files, each carrying an `# adr:` comment pointing here.** **Pattern:** ADR-gated kernel amendment — the sanctioned loud path the fence's error message describes. The fence stays the mechanical gate; the edit becomes auditable.

## Decision

Adopt **Option D.** Three parts:

1. **Re-apply commit `5055292` verbatim** (`git show 5055292` is the source of truth). The fix:
   - `DockerfileProbe.run` writes `raw/dockerfile.json` on **every** exit path — parsed and marker-absent alike — so a consumer can distinguish "dockerfile probe ran, found nothing" from "upstream never ran". The sidecar path is appended to `raw_artifacts`.
   - `RuntimeTraceProbe` routes all five `run()` exit paths (yaml-malformed, image-digest-unresolved, macOS-degraded, all-builds-failed, success) through a single `_finalize()` chokepoint that writes `raw/runtime_trace.json` and prepends it to `raw_artifacts`, so `sbom` and `certificate` always find a typed slice.
   - `entrypoint`, `shell_usage`, `certificate`, `sbom`, `cve` register `runs_last=True` so they dispatch after their sidecar producers. B2's dispatch test relaxes to the load-bearing invariant (B2 in the `runs_last` tail, after every prelude probe whose freshness it checks).
   - `SemgrepProbe` counts rules actually loaded (`time.rules`) instead of distinct finding `check_id`s, and reports an honest `config_absent` skip when zero rules load (a vacuous scan) rather than a misleading clean result. `config_absent` is the existing `ScannerSkipped.reason` value from [Phase 2 ADR-0006](../../02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md) §Amendment 2026-05-21.
   - The `5055292` unit-test updates, golden-file updates (`entrypoint`/`shell_usage`/`certificate` move off the broken `unavailable` baseline), and `docs/get-started.md` FAQ entries ride along as part of the same diff.

2. **Amend `_KERNEL_ALLOWLIST`** in `tests/fence/test_kernel_frozen.py` with the eight touched kernel files, as a single grouped block carrying an inline `# adr:` comment naming this ADR:

   - `src/codegenie/probes/layer_c/dockerfile.py`
   - `src/codegenie/probes/layer_c/runtime_trace.py`
   - `src/codegenie/probes/layer_c/entrypoint.py`
   - `src/codegenie/probes/layer_c/shell_usage.py`
   - `src/codegenie/probes/layer_c/certificate.py`
   - `src/codegenie/probes/layer_c/sbom.py`
   - `src/codegenie/probes/layer_c/cve.py`
   - `src/codegenie/probes/layer_g/semgrep.py`

   The allowlist is "allowed-IF-touched": listing a file does not require editing it; it permits the edits this fix makes. No other kernel file may be edited under this ADR.

3. **Land the regression-guard integration test** `tests/integration/test_layer_c_sidecar_contract.py` — the producer↔consumer seam test that, had it existed, would have caught the original bug. It runs a real `codegenie gather` against a repo *with* a Dockerfile and asserts: (a) every `raw/<name>.json` token any registered probe declares as an input is actually produced by a gather; (b) `entrypoint` and `shell_usage` emit non-`unavailable` slices with a Dockerfile present; (c) `certificate` reaches a non-`unavailable` confidence (proving it consumed the `runtime_trace` sidecar). Test files live under `tests/`, outside kernel scope — they need **no** allowlist row.

The implementation of this decision is Phase 7 story **[S19-01](../stories/S19-01-layer-c-sidecar-publishing.md)**.

## Tradeoffs

| Gain | Cost |
|---|---|
| The Layer C marker probes report honest confidence again; the Phase 7 migration task class sees real Dockerfile / runtime-trace evidence instead of a uniform `unavailable` | Eight Phase 0/1/2 kernel probe files become permanently-permitted kernel edits; the allowlist grows by an eight-file block |
| The kernel-frozen fence stays the mechanical gate — the edit is loud, ADR-reviewed, and the allowlist is the audit trail of which ADR authorized which file | Two consumers of the `git`-diff fence (Phase 3 ADR-0011 + this amendment) must be read together to see why the eight Layer C files are mutable |
| The recovered integration test closes the producer↔consumer seam permanently; any future probe declaring a `raw/<name>.json` input gets the same guarantee for free | The integration test runs a full `codegenie gather` — heavier than a unit test; it must stay in a `make check` lane and not be swept into the bwrap-gated xfail set |
| The fix is a verbatim re-application of a reviewed, known-good commit — low implementation risk | The `runs_last=True` registrations and B2's relaxed dispatch test must be re-verified against any registry changes that landed after `5055292` was reverted |

## Pattern fit

Implements **Mechanical-policy enforcement** — the kernel-frozen fence is a runtime test, not a prose convention; the policy is amended by amending the test's data (`_KERNEL_ALLOWLIST`), exactly as [Phase 3 ADR-0011](../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) intends. Instantiates **ADR amendment by addition** — the allowlist grows by one ADR-reviewed block; no existing entry is edited; mirrors the in-repo precedent where allowlist entries cite cross-phase ADRs (production ADR-0044 rows, Phase 1 ADR-0013 amendment rows, Phase-shakedown F-03/F-06 rows). The `_finalize()` chokepoint in `RuntimeTraceProbe` is **single-exit / functional-core** discipline — five exit paths funnel through one impure persistence step. The allowlist itself stays **data, not branching code**.

## Consequences

- `tests/fence/test_kernel_frozen.py`'s `_KERNEL_ALLOWLIST` gains an eight-file block; `make fence` and `make check` are green after the amendment.
- The eight files are permitted kernel edits **for the scope of this fix only**. A future phase that needs to edit any of them further requires its own ADR — the allowlist entry does not pre-authorize unrelated change.
- **Forward dependency — the Phase 7 byte-edit fence.** [ADR-0009](0009-phase-7-byte-edit-allowlist-fence.md) defines a second, stricter fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) that asserts byte-identity against the Phase 6.5 baseline for every file under `src/codegenie/`. That fence **does not exist yet** — Phase 7 is designed but unimplemented; it is landed by story S5-01. When it lands, it will also flag these eight Layer C/G edits, and ADR-0009's allowlist must enumerate them. This ADR **flags** that dependency; it does not add a row to a file that does not exist (doing so would be the silent drift this discipline forbids). Whoever implements S5-01 must consult this ADR and enumerate the eight files; this ADR is cross-linked from S5-01's story for that reason.
- The recovered integration test (`tests/integration/test_layer_c_sidecar_contract.py`) is the permanent guard. Its `test_declared_raw_sidecar_inputs_are_produced_by_a_gather` case auto-extends: any probe that ever declares a `raw/<name>.json` `declared_input` is checked, for free, that a gather actually produces that sidecar.
- The `entrypoint` / `shell_usage` / `certificate` golden files move off the broken `unavailable` baseline. Those golden updates are part of the re-applied `5055292` diff and are not a separate decision.
- `make check`'s test suite, `make fence`, `make lint-imports`, and `mypy --strict` are all green after S19-01 — no LLM SDK is introduced; the fix is pure deterministic probe code.

## Reversibility

**High.** The allowlist is data in a test fixture — removing the eight-file block is a one-line-per-file deletion. Reverting the amendment reverts to a stricter fence; the eight probe edits would then fail it loudly (which is the correct behavior — a loud failure, not silent drift). Reverting the probe fix itself reverts to the `unavailable`-everywhere bug, which the integration test would then catch as a red — the regression can no longer ship silently.

## Evidence / sources

- Commit `5055292` — "fix(probes/layer_c): publish raw sidecars so marker probes see upstream evidence" (the verbatim source of the re-applied diff).
- Commit `7f6a009` — the revert; its message records the redo-as-Phase-7-story-with-ADR-amendment instruction this ADR executes.
- `tests/fence/test_kernel_frozen.py` — the Phase 3 ADR-0011 fence; `_KERNEL_ALLOWLIST` (lines ~45–235), the `# adr:` comment convention, and the "add the file to the allowlist … via ADR amendment" error message.
- `src/codegenie/probes/layer_b/index_health.py::read_raw_slices` — the consumer-side reader the marker probes use; `entrypoint.py` / `certificate.py` `declared_inputs` — the `raw/<name>.json` tokens.
- [Phase 3 ADR-0011 — honest framing: capability / SandboxedPath / PLUGINS.lock](../../03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md) (the kernel-frozen fence's owning ADR).
- [Phase 2 ADR-0006 — index-freshness sum-type location](../../02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md) §Amendment 2026-05-21 (the `config_absent` `ScannerSkipped.reason` value).
- [Phase 7 ADR-0009 — byte-edit allowlist fence](0009-phase-7-byte-edit-allowlist-fence.md) (the forward-dependency fence).
- CLAUDE.md "Load-bearing architectural commitments — Honest confidence" + "Extension by addition — no *silent* edits".
