# Validation report — S4-01 (`IndexHealthProbe` (B2) + registry-dispatched freshness loop)

**Story:** [S4-01-index-health-probe.md](../S4-01-index-health-probe.md)
**Date:** 2026-05-16
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's intent is sound — the load-bearing B2 probe, `runs_last=True` dispatch, registry-loop Open/Closed seam, and typed `IndexFreshness` are all correct against [phase-arch-design.md §"Component design" #1](../../phase-arch-design.md), [02-ADR-0003](../../ADRs/0003-coordinator-heaviness-sort-annotation.md), [02-ADR-0006](../../ADRs/0006-index-freshness-sum-type-location.md), and [production design.md §2.3](../../../../production/design.md). The *prescriptions*, however, reference six phantom Phase-0/1 surfaces that do not exist on master — every one would stop the executor on its first tool call. Eight BLOCK-severity inconsistencies closed; six harden findings closed; four design-pattern notes added.

## Context Brief

**What the story promises:**
1. `IndexHealthProbe` ships in `src/codegenie/probes/layer_b/index_health.py` with `@register_probe(runs_last=True)`, `cache_strategy="none"`, and `timeout_seconds=10`.
2. The probe's `run()` body is **dispatch-table-on-registry** — zero `if index_name == "..."` branches. The SCIP freshness check is the **only** check this story registers; future index sources register theirs in their owning probe stories.
3. Every failure surface is typed (`Stale(IndexerError(...))`) — the probe never raises.
4. `runs_last=True` is observable: B2's start timestamp is strictly later than every sibling probe's end timestamp.

**What the phase's exit criteria demand:**
- `phase-arch-design.md §"Goals"` — silent index staleness is the worst failure mode of the entire system; B2 is what makes commitment §2.3 real.
- [`High-level-impl.md` Step 4](../../High-level-impl.md) — B2 ships with the stale-SCIP adversarial test green-or-failing-build (S4-02).
- The `stale-scip` adversarial (S4-02) structurally asserts `isinstance(freshness, Stale) AND isinstance(freshness.reason, CommitsBehind) AND freshness.reason.n >= 1 AND freshness.reason.last_indexed != current_HEAD`.

**What the arch + ADRs constrain:**
- 02-ADR-0003: `runs_last=True` is a registry annotation, NOT a `Probe` ABC field. The coordinator hoists `runs_last=True` probes to the tail of the rest wave.
- 02-ADR-0006: `IndexFreshness` lives at `codegenie.indices.freshness` (pure data) and the registry/Open-Closed seam lives at `codegenie.indices.registry` (decorator + `dispatch_all` method).
- Phase 0 ADR-0007: the `Probe` ABC is contract-frozen. `Probe.run(repo, ctx)` is two-argument; `Probe.version` is a *convention*, not a contract field. `ProbeContext` carries `workspace`, `parsed_manifest`, `input_snapshot`, `image_digest_resolver` — **no** `sibling_slices`. The runtime ctx is `BudgetingContext` (no `image_digest_resolver` field wired today either; that's a tracked gap to S1-09).

## Source-of-truth verifications (grep against master)

| Reference in draft | Master surface | Verdict |
|---|---|---|
| `async def run(self, ctx) -> ProbeOutput` | `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` at `src/codegenie/probes/base.py:94`; called as `probe.run(snapshot, ctx)` at `src/codegenie/coordinator/coordinator.py:427` | **PHANTOM** — two-argument signature; story's `ctx.snapshot.root` should be `repo.root` |
| `ctx.sibling_slices.get(index_name)` | `ProbeContext` at `src/codegenie/probes/base.py:51-62` has fields `cache_dir, output_dir, workspace, logger, config, parsed_manifest, input_snapshot, image_digest_resolver`. No `sibling_slices`. Coordinator collects `outputs: dict[str, SanitizedProbeOutput]` but does NOT thread it into subsequent probes' ctx (`src/codegenie/coordinator/coordinator.py:235-260`). | **PHANTOM** — `sibling_slices` field does not exist on the frozen ABC; adding it would be an out-of-scope ADR amendment |
| `iter_freshness_checks()` | `default_freshness_registry: FreshnessRegistry` at `src/codegenie/indices/registry.py:178`; the public dispatch API is `default_freshness_registry.dispatch_all(slices: dict[IndexName, dict[str, object]], head: str) -> dict[IndexName, IndexFreshness]` (line 139) and `default_freshness_registry.registered_names() -> frozenset[IndexName]` (line 128). No `iter_freshness_checks` symbol exists. | **PHANTOM** — wrong function name; the actual API is `dispatch_all`/`registered_names` |
| `_clear_for_tests()` | `FreshnessRegistry.unregister_for_tests(index_name)` at `src/codegenie/indices/registry.py:165` — per-name, NOT a global clear | **PHANTOM** — wrong name and signature |
| `check_fn(slice=sibling, head=head_sha)` | `FreshnessCheck = Callable[[dict[str, object], str], IndexFreshness]` at `src/codegenie/indices/registry.py:56` — **positional** args, **slice param is `dict[str, object]`** (not `dict | None`); `dispatch_all` calls `check(slices.get(name, {}), head)` (line 163) — passes **empty dict**, never `None` | **PHANTOM** — wrong keyword/positional convention; T-08 / AC-12 sibling-missing semantics are wrong |
| `run_allowlisted` raises `FileNotFoundError, subprocess.CalledProcessError, TimeoutExpired` | `run_allowlisted` at `src/codegenie/exec.py:216` raises `DisallowedSubprocessError`, `FileNotFoundError` (cwd missing only — not "git not installed"), `NotADirectoryError`, `ToolMissingError` (binary not on `PATH`), `ProbeTimeoutError`. It does **not** raise `subprocess.CalledProcessError` on non-zero exit — non-zero exits return a `ProcessResult` with `returncode != 0` | **PHANTOM** — wrong exception taxonomy |
| `result.stdout.strip()` (where `result = run_allowlisted(...)`) | `ProcessResult(returncode: int, stdout: bytes, stderr: bytes)` at `src/codegenie/exec.py:139-150` — `stdout` is **bytes**, not `str`; field is `returncode`, not `return_code` | **PHANTOM** — wrong type; needs `.decode("utf-8")` (or `.strip().decode()`) |
| `version="0.1.0"` as a Probe class attribute (AC-1) | `Probe` ABC at `src/codegenie/probes/base.py:74-96` does NOT declare `version`. `registry.py:30-36` docstring states: "`Probe.version` is a *convention*, not part of the frozen ABC" — it's read by cache-key code (`CacheStore.key_for`) via the `_ProbeLike` structural Protocol. | **HARDEN** — keep `version="0.1.0"` (matches Phase 0/1 convention) but the AC must say *"matches the Phase 0/1 `version` convention; not enforced by the frozen ABC"* |

## Critic reports

### Coverage critic — HARDEN

Six findings (F1–F6):

- **F1 — AC-12 sibling-missing assumes `slice=None`, but registry passes `{}`:** The actual `FreshnessRegistry.dispatch_all` calls `check(slices.get(name, {}), head)` — `{}` (empty dict), never `None`. AC-12 + AC-5(a) + T-08 must be rewritten: the check function's slice param is `dict[str, object]`; "upstream unavailable" is detected by `not slice` (empty dict) or by absence of required keys, not by `slice is None`.
- **F2 — `confidence` field collision unclarified:** `ProbeOutput.confidence: Literal["high","medium","low"]` exists at the *envelope* level (one per probe). The story's AC-9 also derives a per-source `confidence` (one per index_name) embedded in the slice. AC-10 must explicitly say the per-source `confidence` is **inside the per-index nested dict** and the *probe-level* `ProbeOutput.confidence` is the demote-min over the per-source values.
- **F3 — Per-source `last_indexed_at` derivation missing for the `Stale` case:** The story's AC-10 says `last_indexed_at: <iso8601 | null>` but doesn't specify when it's `null`. Resolution: `Fresh(indexed_at=dt)` → ISO8601; every `Stale(...)` → `null` (the indexed_at is no longer authoritative). AC-9 / AC-10 must document this.
- **F4 — Empty-slice vs. missing-keys conflation:** A SCIP slice that's present but missing `last_indexed_commit` (malformed) is different from a slice that's empty (upstream skipped). AC-5 must specify a `KeyError`/missing-key path → `Stale(IndexerError("scip_slice_malformed"))`, distinct from `Stale(IndexerError("upstream_scip_unavailable"))`.
- **F5 — Disk-reading mechanism for sibling slices unspecified:** Given `ctx.sibling_slices` is phantom, AND the writer hasn't run yet during B2's `run()`, the story must specify how B2 builds the `slices` dict it passes to `dispatch_all`. The realistic path: sibling probes write their slice-data to `<repo>/.codegenie/context/raw/<index_name>.json` during their own `run()`; B2 reads those files via the `output/paths.raw_dir(repo.root)` helper. AC-4 + Implementation outline must say this explicitly. (The alternative — adding `sibling_slices` to ProbeContext — is a contract-frozen change requiring a Phase-2 ADR amendment and is out of scope for S4-01.)
- **F6 — AC-3 dispatch-order test's coordinator harness underspecified:** The actual coordinator hoists `runs_last=True` probes via `runs_last_names: frozenset[str]` passed to `gather()` (see `coordinator.py:460`). T-03 must reuse that harness shape (call `gather(snapshot, task, probes, config, cache, sanitizer, runs_last_names=frozenset({"index_health"}))`), not invent a synthetic semaphore.

### Test-quality critic — HARDEN

Mutation table for plausibly-wrong implementations the original TDD plan would let through:

| Plausibly-wrong implementation | Original TDD plan catches it? | After hardening |
|---|---|---|
| `_derive_confidence` returns `"high"` for `Stale(IndexerError(...))` (silent floor demotion swallows real failures) | ❌ No — T-13 parametrizes but doesn't pin the *specific* mapping per `StaleReason` variant in a `pytest.mark.parametrize` table | ✅ T-13 rewritten as a four-row parametrize table mapping each `StaleReason` ⇒ exact `confidence` |
| `dispatch_all` is called but its result keys are silently re-keyed (e.g., `name.lower()`), so a future `IndexName("SCIP")` registration silently disappears from the slice | ❌ No — T-20 only checks the per-source keys are `{"freshness", "confidence", "current_commit", "last_indexed_at"}`, not that the *outer* keys equal `IndexName` registrations | ✅ AC-10 / T-20: outer-key invariant added — `set(results.keys()) == set(default_freshness_registry.registered_names())` |
| The `git rev-parse HEAD` byte-string is `.strip()`-ed but not decoded, leaving a `bytes` value flowing into `current_commit` | ❌ No — story uses `.stdout.strip()` on bytes, type-check would catch it but only if a strict annotation is in place | ✅ AC-6 + implementation outline pin `.stdout.decode("utf-8").strip()` AND a `head: str` annotation on the local |
| `runs_last=True` works in unit test but coordinator hoist isn't wired (registry annotation set but seam doesn't pass `runs_last_names`) | ⚠ Partial — T-02 checks registry entry, T-03 checks ordering, but neither asserts the CLI seam passes the set | ✅ AC-3 adds: "the CLI seam `_seam_coordinator_gather` passes `runs_last_names={'index_health'}` derived from `default_registry.sorted_for_dispatch()`" |

### Consistency critic — BLOCK (eight findings, all resolved)

- **B1:** `Probe.run` signature is two-arg (`repo`, `ctx`) — story's one-arg signature would not even import.
- **B2:** `ctx.sibling_slices` doesn't exist — see F5.
- **B3:** `iter_freshness_checks()` doesn't exist — actual API is `dispatch_all(slices, head)` + `registered_names()`.
- **B4:** `_clear_for_tests` doesn't exist — actual is `unregister_for_tests(index_name)`.
- **B5:** `FreshnessCheck` signature is positional `(dict[str, object], str)` — story's `slice=…, head=…` keyword call is wrong; sibling-missing is `{}` not `None`.
- **B6:** `run_allowlisted` exception taxonomy is wrong (raises `ToolMissingError`/`ProbeTimeoutError`/`DisallowedSubprocessError`, does NOT raise `CalledProcessError` on non-zero exit).
- **B7:** `ProcessResult.stdout` is `bytes`, field is `returncode` (not `return_code`).
- **B8:** `Probe.version` is a convention, not an ABC field — AC-1 must say so explicitly to avoid a contract-drift trap.

### Design-pattern critic — four notes (DP1–DP4)

- **DP1 — `dispatch_all` IS the no-branches enforcement.** The actual `FreshnessRegistry.dispatch_all` is the single call that loops registered checks. The story's "AST-walk verifies no per-index branches" (T-15) is still valuable defense-in-depth, but the *primary* enforcement is that B2's `run()` calls `dispatch_all(slices, head)` exactly once. Reframe T-15 around the structural invariant.
- **DP2 — Pluggable sibling-slice reader (functional core).** The disk-reading step (F5) is a pure function `read_raw_slices(raw_dir: Path) -> dict[IndexName, dict[str, object]]`. Keep it module-level so tests can inject in-memory slices without touching disk. Mirrors the `_derive_confidence` pure-helper discipline.
- **DP3 — Smart constructor + `assert_never` ladder closed at B2.** B2 is the *producer*; S8-01's `confidence_section.py` is the *consumer*; both ends exhaustively `match` on `IndexFreshness`. Document the producer-consumer pairing in module docstring.
- **DP4 — `IndexName` newtype rule-of-three reached at S4-01.** S1-02 (1st use — registry key), S5-05 (2nd — runtime_trace registration), S4-01 (3rd — B2 enumerates registered names). The kernel-extract opportunity (`KernelRegistry[K, V]` base across `codegenie.probes.registry`, `codegenie.indices.registry`, `codegenie.depgraph.registry`) crosses the rule-of-three threshold here — surface in Notes-for-implementer as deferred to a dedicated refactor story (out of scope for S4-01 per Rule 2 / Rule 3).

## Stage 3 research

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from:
- arch design (`phase-arch-design.md §"Component design" #1, #2`, `§"Data model"`, `§"Process view"` load-bearing properties 1 & 3, `§"Harness engineering"`);
- ADRs 02-ADR-0003 (registry annotations), 02-ADR-0006 (IndexFreshness location + variant set), 02-ADR-0007 (no plugin loader; `Probe.version` is convention);
- verified live source: `src/codegenie/probes/base.py:74-96`, `src/codegenie/indices/registry.py:139-175`, `src/codegenie/indices/freshness.py`, `src/codegenie/exec.py:140-272`, `src/codegenie/coordinator/coordinator.py:425-510`, `src/codegenie/probes/registry.py:198-220`, `src/codegenie/output/paths.py`;
- sibling validations (S2-01, S2-02, S3-03 used the same pattern of "phantom Phase-0 surface vs. master").

## Edits applied

| AC / section | Original | After hardening |
|---|---|---|
| Story header — Validation notes block | absent | New block summarizing eight BLOCK fixes + six harden + four design notes |
| Goal | `Running ... ctx.sibling_slices.get(index_name)` implied | Reworded: B2 reads sibling slices from `<repo>/.codegenie/context/raw/*.json` via the pluggable `read_raw_slices` helper; the contract surface (`Probe.run(repo, ctx)`) and `ProbeContext` are untouched |
| AC-1 | `async def run(self, ctx) -> ProbeOutput`; `cache_strategy: Literal["none"] = "none"`; `version="0.1.0"` claimed as ABC attribute | `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`; explicit note that `version` is the Phase 0/1 convention, not an ABC field; `requires: list[str] = []` (the ABC uses `str`, not `ProbeId`) |
| AC-3 | "synthetic registry test ... `Semaphore(min(cpu_count(), 8))`" | Real-coordinator harness via `gather(..., runs_last_names=frozenset({"index_health"}))`; ALSO the CLI-seam check that `default_registry.sorted_for_dispatch()` returns the index_health entry **last** |
| AC-4 | "loops `codegenie.indices.registry.iter_freshness_checks()`" | "calls `default_freshness_registry.dispatch_all(slices, head)` exactly once" + pluggable `read_raw_slices(raw_dir) -> dict[IndexName, dict[str, object]]` step |
| AC-5 | `check_fn(slice=sibling, head=head_sha)` keyword call; `(a) slice is None → Stale(IndexerError("upstream_scip_unavailable"))` | Positional call matching `FreshnessCheck` alias; `(a) slice is empty dict (or missing required keys) → Stale(IndexerError("upstream_scip_unavailable"))`; new branch (f) malformed slice (key type mismatch) → `Stale(IndexerError("scip_slice_malformed"))` |
| AC-6 | "parsed as `int`" — no decode mention | `.stdout.decode("utf-8").strip()` for the rev-list count; `head` is `bytes.decode("utf-8").strip()`; both annotated `: str` |
| AC-7 | "If `run_allowlisted` raises `FileNotFoundError`, `subprocess.CalledProcessError`, or `TimeoutExpired`" | "If `run_allowlisted` raises `ToolMissingError`, `DisallowedSubprocessError`, `ProbeTimeoutError`, or `FileNotFoundError` (cwd missing), OR returns a `ProcessResult` with `returncode != 0`" |
| AC-9 | per-source `confidence` derivation rules | Same rules + explicit "`ProbeOutput.confidence` (envelope-level) is the demote-min over the per-source confidences; `low > medium > high`" |
| AC-10 | per-source slice keys + `last_indexed_at: <iso8601 \| null>` | Same + explicit "outer keys of the `index_health` slice equal `default_freshness_registry.registered_names()` byte-for-byte"; `last_indexed_at` is `null` on every `Stale` variant |
| AC-12 | "if `ctx.sibling_slices.get(index_name)` is `None`, the check function emits `Stale(IndexerError(message=f"upstream_{index_name}_unavailable"))`" | "if `slices.get(index_name, {})` is `{}` (the registry's sentinel for absent sibling slice), the check function emits `Stale(IndexerError(...))`. B2 does NOT branch on this case — the check function is the right shape." |
| AC-13 | "imports ONLY from ..., `codegenie.exec`, and stdlib" | Same set + `codegenie.types.identifiers` (for `IndexName`) + `codegenie.output.paths` (for `raw_dir`) + `codegenie.errors` (typed exception catch) |
| Implementation outline | `iter_freshness_checks` loop; `ctx.snapshot.root`; bytes/str conflation | `default_freshness_registry.dispatch_all`; `repo.root`; `read_raw_slices(raw_dir(repo.root))`; `head = result.stdout.decode("utf-8").strip()`; `try` body catches `ToolMissingError/ProbeTimeoutError/DisallowedSubprocessError/FileNotFoundError` AND checks `result.returncode != 0` |
| TDD helpers preamble | `from codegenie.indices.registry import register_index_freshness_check, iter_freshness_checks, _clear_for_tests` | `from codegenie.indices.registry import default_freshness_registry, register_index_freshness_check` + custom `clean_freshness_registry` fixture that records and re-stores the singleton's `_checks` dict |
| T-04..T-08 | `slice=<dict>, head=<sha>` keyword | Positional `(slice_dict, head)` matching `FreshnessCheck` alias |
| T-08 | "sibling slice is `None`" | "registry's `dispatch_all` invokes the check with `{}` — the empty-dict sentinel" |
| T-15 (no-per-index-branches AST test) | "AST-walk `IndexHealthProbe.run`" | Same + a complementary positive assertion: `run()` contains exactly one `await default_freshness_registry.dispatch_all(...)` call (structural one-entry-point invariant) |
| Notes-for-implementer | duplicated from arch | + DP1 (`dispatch_all` IS the enforcement) + DP2 (pluggable `read_raw_slices`) + DP3 (producer/consumer assert_never ladder) + DP4 (`IndexName` rule-of-three deferred refactor) + explicit gotcha: SCIP probe (S4-03) MUST write `<repo>/.codegenie/context/raw/scip.json` during its `run()`, otherwise B2 sees an empty slice and emits `Stale(IndexerError("upstream_scip_unavailable"))` — this is the cross-story integration handoff |

## Verdict rationale

**HARDENED.** The story's design intent (load-bearing B2, `runs_last=True`, registry-loop Open/Closed) traces cleanly to the arch + ADRs. The eight BLOCK-severity inconsistencies all derive from prescriptions written against a hypothetical surface that the executor would have abandoned on first tool call. After hardening:

- All BLOCK findings closed by realigning prescriptions to actual master surfaces (`Probe.run(repo, ctx)`, `default_freshness_registry.dispatch_all`, `unregister_for_tests`, `ProcessResult.stdout: bytes`, the `ToolMissingError/ProbeTimeoutError` taxonomy, `Probe.version` as convention).
- The sibling-slice reading mechanism is now explicitly grounded: disk-read via `output/paths.raw_dir(repo.root)` glob, mediated by a pluggable `read_raw_slices` pure helper. Contract is untouched.
- Test-quality gaps (parametrize mapping per `StaleReason`, outer-key invariant, bytes→str decode pin, CLI-seam wiring) closed.
- Design-pattern opportunities (no-branches-via-single-dispatch_all, pure functional-core helpers, producer/consumer `assert_never` pairing, `IndexName` newtype rule-of-three threshold) surfaced in Notes-for-implementer; no premature kernel-extract per Rule 2.

Ready for [phase-story-executor](../../../../../skills/phase-story-executor).
