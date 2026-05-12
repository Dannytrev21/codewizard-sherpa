# Phase 01 — Context gathering: Layer A (Node.js): Devil's-advocate critique

**Reviewed by:** Devil's-advocate critic subagent
**Date:** 2026-05-12

## Method

I read all three designs and attacked each on its own terms. I do not propose alternatives. My job is to surface what the synthesizer needs to see before it merges.

I checked each design against:
- Phase 0's final-design.md (the locked spine) and its ADRs 0001–0013.
- `localv2.md §4` (the frozen probe contract).
- `production/design.md §2` load-bearing commitments.
- The roadmap's Phase 1 scope ("Real Layer A probes ... cache hits on second run ... all probes pass schema validation").

---

## Attacks on the performance-first design

### Concrete problems

1. **Problem:** The "PathIndex-aware Probe mixin" is a second class hierarchy alongside the frozen `Probe` ABC.
   **Why it matters:** Phase 0 §2.3 freezes `codegenie/probes/base.py` byte-for-byte to `localv2.md §4` via a snapshot test fingerprinted against `localv2.md` content. Any Phase 1 probe that inherits *both* `Probe` *and* `PathIndexAwareMixin` either (a) drifts the snapshot (CI fails) or (b) doesn't actually change the ABC and instead introduces an out-of-band `coordinator.use_path_index(probe, idx)` hook that the contract has no concept of. Phase 0 §12 "Phase 1 inherits and may not change without ADR amendment" lists "Probe ABC" first.
   **Where:** §"Components" #3 "PathIndex-aware Probe mixin (`codegenie/probes/path_index_aware.py`)" — "Sets `self._idx`. ... A second class hierarchy alongside `Probe`."

2. **Problem:** The msgpack inter-probe cache (`.parsed/package.json.msgpack`) silently breaks Phase 0's structural trust boundary.
   **Why it matters:** Phase 0 §2.7 enumerates the Cache API as exactly `get(key) / put(key, output) / key_for(...)`. Phase 0 §2.8 names the OutputSanitizer "the only path from `ProbeOutput` to persisted artifact." Writing `.parsed/package.json.msgpack` to `ctx.workspace` is a second persistence path that bypasses both `_ProbeOutputValidator` (no Pydantic check on `msgpack.loads` output) and `OutputSanitizer` (no field-name regex on the cached dict). The design itself admits "Inter-probe sharing without violating the ABC: the contract still says 'I read declared_inputs'; the implementation just notices the parsed form is available" — which is exactly violating the contract by side channel.
   **Where:** §"Components" #5 "NodeBuildSystemProbe ... `package.json` is parsed exactly once per gather by `NodeManifestProbe` and the parsed dict is stuffed into `ProbeContext.workspace` as a sibling file `.parsed/package.json.msgpack`".

3. **Problem:** The performance design openly proposes flipping Phase 0's no-mmap decision based on a Phase 14 workload that doesn't exist yet.
   **Why it matters:** Phase 0 conflict-table row 14 says "Plain buffered read" with scores E=3,R=3,C=3,Cr=2; mmap was vetoed because "concurrent CLI processes mmap'ing an `O_APPEND` index is a race." This design's "I push back: macOS dev workstations are not the portfolio-scale target" reopens a settled fight in a phase whose only obligation is to populate the contract Phase 0 wrote. Phase 1 should not be the place where a Phase 14 measurement decides anything — the design admits "if Phase 0 stays no-mmap, my numbers move by ~5%."
   **Where:** §"Components" #10 "Cache-layer hot path" — "mmap of the on-disk index is now a yes. Phase 0 deferred mmap..."

4. **Problem:** Hand-rolled `yarn.lock` parser is justified to save ~200 ms on the warm path that the design itself says is dominated by cache hits.
   **Why it matters:** The design's own resource profile shows incremental p50 ~180 ms is dominated by SnapshotBuilder + LRU; cache hits skip parsing entirely. The hand-rolled parser only matters on lockfile-changed (cache-miss) gathers, which by the design's own steady-state cache-hit-rate target (≥ 92%) are 8% of runs. 200 ms × 0.08 = ~16 ms per *average* gather. A ~1k LOC hand-rolled parser is being justified by 16 ms of average latency on a phase whose roadmap exit criterion is "useful `repo-context.yaml`." Rule 2 (Simplicity First) and Rule 9 (test verifies intent — what test would catch a parser bug *and* fail on benign yarn.lock evolution?) both bite.
   **Where:** §"Components" #6 NodeManifestProbe — "Hand-rolled `yarn.lock` parser is a maintenance liability."

5. **Problem:** `views.json` ships in Phase 1 for a Phase 8 consumer that hasn't been designed.
   **Why it matters:** ADR-0013 (the citation given) is a deferred ADR. Phase 8's hot-view list is unspecified. The design pre-commits to four slice names (`available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) and a JSON shape, ships `views.schema.json`, and adds a streaming-write pass — all in a phase whose scope is six Layer A probes. The blast radius if Phase 8 changes the slice list is "Phase 1 follows" — which is, by definition, editing Phase-1 code from Phase 8. That is the inverse of `production/design.md §2.5` (extension by addition: *new* files, never edits).
   **Where:** §"Components" #11 "Streaming writer + hot-view projection" — "views.json sibling artifact. ... Pre-shaping for the Phase 8 hot path is the explicit cite of ADR-0013 — I'm doing the projection work now, two phases early..."

6. **Problem:** Adding `msgpack`, `pyjson5`/`orjson`, `ruamel.yaml` and `blake3` (already in Phase 0) inflates the gather extras closure with three new C-extension dependencies — and the `fence` test verifies *no LLM SDKs*, not *no fast-parser drift*.
   **Why it matters:** Each new C extension is a new CVE feed to follow, a new wheel build for every platform in the matrix, and a new mypy-stubs problem. The design explicitly says "Bench at integration time; if `pyjson5` underperforms a fork to `orjson` with a strip-comments pass, switch" — i.e., it ships an unresolved bench-the-winner-later decision. Phase 0 ratified `pyyaml.CSafeLoader` + stdlib `json` + `blake3`; the design adds three more without naming the trigger that requires them.
   **Where:** §"Components" #5–6 — `msgpack`, `pyjson5`/`orjson`, `ruamel.yaml` mentions; §"Open questions" #4 "`pyjson5` vs `orjson` + comment-strip vs sticking with stdlib `json`".

### Hidden assumptions

1. **Assumption:** The PathIndex fingerprint is a sufficient cache key for the in-process LRU on `LanguageDetection`.
   **What breaks if it's wrong:** The design admits this: "PathIndex fingerprint matches but on-disk filesystem changed under our feet — e.g., a parallel git checkout" → "Next gather invalidates; correctness preserved at the cost of one extra warm gather." The first gather after the swap returns stale data. For the "first transform" in Phase 3 reading that stale data, "one extra warm gather" later does not undo the wrong diff. This is exactly `production/design.md §2.3` (Honest confidence — silent staleness is the worst failure mode).

2. **Assumption:** Hash-validation skipping on LRU read is safe ("the LRU only holds outputs that were validated when they were inserted").
   **What breaks if it's wrong:** The `_ProbeOutputValidator`'s field-name regex set is mutable — Phase 0 §2.3 lists `(?i)^.*(secret|token|password|credential|...).*$`. If Phase 2 adds a new pattern (e.g., `aws_session_token`), in-process LRU entries inserted before the bump are returned without re-validation. The design's own §"Acknowledged blind spots" admits "If the validator's invariants change (e.g., new secret regex), LRU entries don't re-validate." That's a Rule 12 (fail loud) violation by construction.

3. **Assumption:** Per-probe RSS budgets can be enforced advisory-only without compromising the warm-path numbers.
   **What breaks if it's wrong:** The design's NodeManifest budget (80 MB) is one C-extension allocation away from breaching. A pathological lockfile that allocates 500 MB inside `ruamel.yaml` C-mode silently OOMs the worker because no hard cap exists. The risks section admits this and proposes "Open question for the synthesizer." That's a punt, not a design.

4. **Assumption:** "Tier-0 probes are pure-Python parse work; the GIL is irrelevant because we're parsing JSON/YAML, which releases the GIL in the C parsers."
   **What breaks if it's wrong:** This claim is partly false: `json.loads` releases the GIL only inside `_json.c`'s scanner — not during the Python-dict construction that follows. `pyyaml.CSafeLoader` similarly. Multiple "Tier-1 probes in the same event loop" will serialize on the GIL during dict construction. The asyncio-no-process-pool assumption breaks on the cold path the design openly de-prioritized.

### Things this design missed that a different lens caught

- **Adversarial inputs.** Zero mention of YAML billion-laughs, JSON-bomb depth caps, or `O_NOFOLLOW` on the BLAKE3 hashing pass. The security design's threat model is the load-bearing rebuttal to ~30% of this design's perf wins (e.g., reading file bytes for cache-key derivation is required for poisoning resistance, not just optional).
- **`additionalProperties: false` per probe sub-schema.** Best-practices makes this load-bearing; perf design never mentions it. A perf-shaped slice that omits a field will silently pass through under Phase 0's `probes.*: additionalProperties: true`.
- **The roadmap exit criterion.** Roadmap says "useful `repo-context.yaml` ... cache hits on second run ... all probes pass schema validation." Perf design's targets ("≥ 2,400/hr ... 92% cache-hit ... 250 ms incremental p95") are not derivable from the roadmap; the design's own §"Open questions" #7 admits this divergence.

---

## Attacks on the security-first design

### Concrete problems

1. **Problem:** The parser sandbox is a brand-new architectural layer that Phase 0 never sanctioned, and it inverts Phase 0's coordinator-runs-probe-in-event-loop model.
   **Why it matters:** Phase 0 §2.6 specifies "One `asyncio.Task` per probe via `asyncio.create_task` + `asyncio.wait_for(timeout=timeout_s)`. ... No thread pool. Probes that shell out use `asyncio.create_subprocess_exec` (via `exec.run_allowlisted`)." This design routes *every* probe through `python -m codegenie.probes._sandbox` — i.e., a fork+exec of the codegenie wheel itself per probe. That requires a new `codegenie.probes._sandbox` entry point (a module the Phase 0 layout does not include), a new IPC contract over stdout JSON (a parser surface inside the *parent* that the design itself notes is "JSON, not pickle"), and a new process-tracking table (mentioned in §"Coordinator" but not designed). This is not "extension by addition" — it changes how every probe runs.
   **Where:** §"Components" → "Parser Sandbox" + §"Architecture" diagram showing `python -m codegenie.probes._sandbox <probe-module>` between every coordinator and probe.

2. **Problem:** Per-probe ~150–300 ms fork+exec overhead × 6 probes = ~1.5 s of pure overhead on every cold-cache gather, and the design's own resource-profile admits this puts CI past Phase 0's ≤ 90 s p95 budget.
   **Why it matters:** Phase 0 §3.2's CI walltime budget is a measured commitment. The design says "We exceed the Phase 0 target deliberately; the security gate is worth the spend" — but Phase 0 §3.2 lists six parallel jobs at ~70–90 s wall-clock total, with `security` already at ~30–40 s. Adding 1.5 s × N test fixtures of cold-cache gather to the `test` job is not 20 s; it scales with the adversarial fixture count (≥ 50 hostile inputs per the design's own goal), each requiring a fresh sandbox. The implicit math is closer to "CI walltime grows linearly with adversarial corpus size."
   **Where:** §"Resource & cost profile" — "Sandbox fork-and-exec overhead. ~150–300 ms per probe execution. Six Layer A probes × cold cache = ~1.5 s wall-clock added."

3. **Problem:** "Cache-key derivation reads file bytes for content hash" reverses an explicit Phase 0 decision.
   **Why it matters:** Phase 0 §2.10 says LanguageDetectionProbe's cache key is "the BLAKE3 hash of the sorted set of (path, size) tuples for files matching `declared_inputs` after exclusion." Phase 0's whole Cache API and key derivation is locked behind ADR amendments per §12. This design's "the cache key derives from the byte content of every file matching `declared_inputs`" rewrites §2.7 + §2.10 simultaneously, citing a poisoning threat for which the Phase 0 critique already evaluated and which Phase 14 was deemed the right layer for. The design admits this would force re-hashing every input on every gather (cache-miss path) but never quantifies the *cache-key derivation* cost separately from cache-miss parse cost — they're conflated.
   **Where:** §"CacheStore" — "Phase 1 changes *what content is addressed*: the cache key derives from the **byte content of every file matching `declared_inputs`**, not the file paths or `(path, size)` tuples."

4. **Problem:** `bwrap` is an undeclared runtime dependency. Linux-only enforcement; macOS gets `sandbox-exec` (deprecated by Apple); Windows is "not supported." But Phase 0's CI matrix is `ubuntu-24.04` and the design's own §"Risks" #1 admits "The sandbox is bypassable on macOS dev hosts."
   **Why it matters:** This collapses the security claim. Either (a) `bwrap` is a hard dep and Phase 1 changes the supported-platforms story Phase 0 set, or (b) it isn't and the "every probe runs in a parser sandbox with rlimits enforced" goal is in fact "on Linux, mostly; on macOS, half." The §"Goals" 2nd item ("Every probe runs in a per-execution parser sandbox with rlimits enforced. No probe parses adversarial bytes in the coordinator process.") is structurally not satisfiable on macOS. Goal #1 ("Zero successful parse-driven RCE against the Phase 1 adversarial fixture corpus") is therefore platform-conditional, which is not how the goal is stated.
   **Where:** §"Parser Sandbox" → "On macOS: `sandbox-exec` with an inline profile ... Documented as best-effort because `sandbox-exec` is deprecated; no security claim is staked on macOS isolation beyond rlimits + env strip."

5. **Problem:** The third sanitizer pass (size/depth caps) and the layered `additionalProperties: false` per Layer A probe are layered onto Phase 0's `OutputSanitizer.scrub` (Phase 0 §2.8) — which Phase 0 §12 explicitly freezes.
   **Why it matters:** Phase 0 fixed the sanitizer at two passes: field-name regex + path scrub. Adding pass 3 inside `OutputSanitizer.scrub` *is* an edit to a frozen component, not an extension. The right reading of `production/design.md §2.5` says new passes go behind a new symbol (e.g., `OutputSanitizer.scrub_v2` or a new validator at a different seam). The design doesn't address whether this triggers the ADR-amendment workflow Phase 0 §12 mandates.
   **Where:** §"Output Sanitizer — modifications to Phase 0" — "Phase 1 adds a third pass. ... 3. NEW: Size/depth cap on `schema_slice`."

6. **Problem:** The "`NodeBuildSystemProbe` does not call `node --version`" decision contradicts `localv2.md §5.1 A2` and the design admits it.
   **Why it matters:** Phase 0 §2.3 makes `localv2.md` the source of truth for the contract, and §12 makes "new external-tool checks in the startup readiness scan" an extension Phase 1 *is expected* to add (via ADR amendment). The design's "this design says no. `localv2.md §5.1 A2` says yes" surfaces the conflict but punts to the synthesizer ("My recommendation is no, but I want this argued explicitly"). That's a Rule 11 conformance violation in lens form: best-practices and `localv2.md` say "read both"; security unilaterally vetoes.
   **Where:** §"NodeBuildSystemProbe" — "**Does not call `node --version`** in Phase 1 (despite `localv2.md` mentioning it)"; §"Open questions" #3.

### Hidden assumptions

1. **Assumption:** "Strings that look like prompt-injection payloads are preserved verbatim and *tagged* via a separate probe-side metadata field (`prompt_injection_marker_count`)."
   **What breaks if it's wrong:** The metadata field is in the schema slice. The Phase 0 envelope `additionalProperties: false` is at the root, with `probes.*: additionalProperties: true` — i.e., Phase 1 probes can in principle emit `prompt_injection_marker_count` without schema-rejecting. But the design itself wants `additionalProperties: false` at the per-probe sub-schema (per its goals #5/9). So either the field is in every sub-schema (an across-the-board edit), or the schema rejects it. The design doesn't reconcile.

2. **Assumption:** "An attacker with concurrent write access to the analyzed repo could swap the file ... in production gather (Phase 14), gather operates on a freshly-cloned worktree, not a shared workspace."
   **What breaks if it's wrong:** Phase 1's actual runtime model is *local CLI on engineer workstations*. The Phase 14 worktree model doesn't exist yet. The TOCTOU between cache-key derivation and sandbox read is real today; the mitigation is a phase that hasn't shipped. Rule 12 says fail loud — the design instead defers the threat to a future phase whose design hasn't been drafted.

3. **Assumption:** `additionalProperties: false` at the per-probe sub-schema "Adding a field to a probe's output requires editing both the probe code and its sub-schema in the same PR — this is friction, and the friction is the point."
   **What breaks if it's wrong:** Phase 0's conflict-table row 4 explicitly picked layered (`false` at envelope, `true` at `probes.*`, sub-schemas per probe). Best-practices and security both want `false` at the sub-schema root in Phase 1. But the Phase 0 row-4 winner says nothing about per-probe sub-schema policy in Phase 1; it leaves room. Both lenses claim load-bearing-ness for the strict policy; only one design (best-practices) actually does the work of saying which schema files own which fields. Security's adoption of `additionalProperties: false` floats free of a sub-schema file list.

4. **Assumption:** "Reading file bytes for cache-key derivation is slower than reading sizes ... well within the 90s CI budget."
   **What breaks if it's wrong:** This argument compares against the per-gather budget, not the *adversarial fixture corpus* budget. ≥ 50 adversarial fixtures × byte-content cache-key derivation × sandbox spin-up = total CI cost the design never sums.

### Things this design missed

- **The `_sandbox` entry point's own ABC.** What types cross the JSON-over-stdout boundary? `ProbeOutput` is a dataclass with `Path` objects in `raw_artifacts`; JSON doesn't have `Path`. The design says "Pydantic, JSONValue" on the way back in, but skips the serialization shape going out.
- **The "Output Sanitizer two-pass chokepoint" ADR (Phase 0 ADR-0008).** Adding a third pass without naming the ADR or proposing an ADR amendment is the exact governance failure Phase 0 §12 was designed to prevent.
- **`localv2.md §5.1 A6` test counts.** The design's "Test files are *enumerated* (count by extension/pattern) but **not parsed**" matches `localv2.md` but agrees coincidentally with the perf design's "We don't actually count tests; we count test *files*." Two lenses agreed, but neither cites the other or the `localv2.md` schema — accidental agreement is fragile.
- **Cache-key versioning at probe-version bump.** Phase 0 §2.7 already includes `probe_version + schema_version` in the cache key. The security design's bytes-of-files derivation is silent about whether a `schema_version` bump still invalidates correctly when the inputs are unchanged — does the bump-and-stale case interact with the byte-content hash? Not analyzed.

---

## Attacks on the best-practices design

### Concrete problems

1. **Problem:** "0 new public modules. ... ≤ 12 files total. ... Net new lines of `src/` Python ≤ 1100 lines, hard ceiling 1500" — these targets read as discipline but are policed nowhere.
   **Why it matters:** Rule 4 (Goal-Driven Execution — define success criteria) is satisfied only if the success criteria can be checked. Where's the CI gate that fails on the 12th file or the 1501st line? The test plan §"Unit tests" lists ~150 tests; the line ceiling is implausible against that footprint. The design admits this implicitly: "target ≤ 1100, hard ceiling 1500" — there is no enforcement, and "hard ceiling" without a CI step is wishful.
   **Where:** §"Goals (concrete, measurable)" — net-new files, net-new line counts.

2. **Problem:** `LanguageDetectionProbe` reads `package.json` *itself* "rather than depending on `NodeManifestProbe` having already run."
   **Why it matters:** Phase 0 §2.10 already shipped `LanguageDetectionProbe` with `declared_inputs = ["**/*.js", "**/*.mjs", ...]` — no `package.json`. Extending the declared_inputs to include `package.json` is fine, but the design's framing ("Phase 0 deliberately shipped a subset with the rest deferred to Phase 1") is wrong: Phase 0 §2.10 deferred *Dockerfile detection* explicitly and made no commitment about framework hints. The extension is an in-place edit to a Phase-0 file the design itself calls "Phase 0 file, extended in place — this is **not** an exception to extension-by-addition." That's a self-justification; the production §2.5 commitment says new probes via new files. Either `LanguageDetectionProbe` is the Phase-0 probe (and Phase 1 extends it via a *new* probe like `LanguageFrameworkProbe`), or the rule is bent.
   **Where:** §"Components" → "LanguageDetectionProbe (extension, not new)".

3. **Problem:** "We use the `pyarn` library on PyPI if it remains widely supported as of Phase 1 land, falling back to a small hand-rolled parser otherwise."
   **Why it matters:** This is a Rule 10 (Checkpoint after every significant step) and Rule 12 (Fail loud) violation by design. The choice is deferred to "land-time"; whoever implements Phase 1 inherits an undecided question. The risks section says "Mitigation: at land-time, the implementer confirms..." — the implementer is not the architect. The fallback also assumes a 100-line hand-rolled `yarn.lock` parser is "simple"; the performance design treats the same thing as a maintenance liability. Two lenses, opposite conclusions, no resolution.
   **Where:** §"Components" → NodeManifestProbe; §"Risks" #4; §"Open questions" #2.

4. **Problem:** Multi-environment Helm/Kustomize outputs as a list when `localv2.md §5.1 A5`'s example shows a singleton — and the design's response is "we report this as a doc-update candidate."
   **Why it matters:** Phase 0 §2.3 makes `localv2.md` the source of truth: "Resolution policy in the ADR amendment: `localv2.md` is the source of truth; the implementation must conform. A drift between code and `localv2.md` is always resolved by changing code, never by editing `localv2.md` to match." Best-practices proposes the inverse — emit a list, document a deviation, file a doc-update PR. Rule 11 (conformance > taste) and Phase 0's `localv2.md`-is-source rule both bite.
   **Where:** §"Components" → CIProbe ("this is a small departure from `localv2.md §5.1 A4`'s example output"); §"Risks" #2.

5. **Problem:** Coverage ratchet from 85/75 → 90/80 is stated as a Phase-1 commitment but acknowledged as possibly unreachable.
   **Why it matters:** Phase 0 conflict-table row 9 explicitly picked "85/75 ratcheting" with the rationale "90/80 with 5 tests is satisfiable only by gameable integration tests (Rule 9 violation)." Phase 1 has more tests, but `deployment.py`'s narrow branches are exactly the case Phase 0 anticipated. The design's mitigation — "lower the per-module floor for `deployment.py` to 85% and surface it explicitly in the PR" — is the gameable carve-out Rule 9 warned about. Either the ratchet is real (and a probe with structurally-narrow branches needs more test-shape redesign) or it's negotiable (and the ratchet is theater).
   **Where:** §"Risks" #5.

6. **Problem:** "Each Phase 1 probe re-reads `package.json` rather than depending on another probe's parsed output" — celebrated as isolation but breaks Phase 0's cache-hit pass-through model.
   **Why it matters:** If three Layer A probes (`LanguageDetection`, `NodeBuildSystem`, `NodeManifest`) each parse `package.json` on every cache-miss gather, the warm-path latency is 3× what it could be. The design accepts this — "violates DRY by a small margin" — but Phase 0 §2.6 just shipped `ProbeExecution ∈ {Ran, CacheHit, Skipped}` precisely to make pass-through cheap. Best-practices doesn't use it. The perf design's msgpack hack solves the wrong problem; best-practices' DRY-violation solves the same problem by inversion. Neither lens names the right seam (probe-output dependency in the coordinator's DAG).
   **Where:** §"Components" → "LanguageDetectionProbe ... Tradeoffs accepted: `LanguageDetection` reads `package.json` *itself* rather than depending on `NodeManifestProbe` having already run."

### Hidden assumptions

1. **Assumption:** "Cyclomatic complexity ceiling per function: 10 (enforced via `ruff` rule `C901`). ... The lockfile parser will likely sit at 8–9 — close, but inside the bound."
   **What breaks if it's wrong:** Three lockfile formats × parser nesting × confidence-downgrade paths means the actual parser sits closer to 12–15 in any honest implementation. The "close, but inside" claim is an estimate without a fixture. The implementer either suppresses `C901` (Rule 12 violation: the design says "zero `# noqa`") or splits the parser into helpers that pass cleanly but obscure the control flow.

2. **Assumption:** "`node --version` cross-check (optional, gated by tool-readiness): if `node` is in `ALLOWED_BINARIES` and on `$PATH`, call `node --version` via `exec.run_allowlisted`."
   **What breaks if it's wrong:** Phase 0 §2.5 `ALLOWED_BINARIES = frozenset({"git"})` is *frozen at module scope*. Adding `node` is the "each binary addition requires its own ADR amendment per Phase 0 §2.5" the design acknowledges. But the design lists `node` as the only `ALLOWED_BINARIES` addition in Phase 1 without writing the ADR amendment, only "an ADR amendment in Phase 1." The amendment is the work; assuming it lands is the assumption.

3. **Assumption:** "The native-module catalog ships in Phase 1 with the well-known set (bcrypt, sharp, better-sqlite3, node-canvas, node-rdkafka, node-pty, bufferutil, utf-8-validate, argon2, keytar)."
   **What breaks if it's wrong:** The catalog's blast radius is named ("the system's blast radius for distroless migration accuracy") but the seed list is hand-picked from popular packages, not from a derivation. A missed entry surfaces in Phase 7 — five phases later. There is no Phase-1 test that asserts the catalog covers the npm top-N native packages; there's only a "Phase 7's integration tests *will* exercise the catalog and surface gaps." That is exactly silent staleness (`production/design.md §2.3`).

4. **Assumption:** All five Phase 1 probes declare `applies_to_languages = ["javascript", "typescript"]` and the coordinator's `for_task` filter handles non-Node repos gracefully.
   **What breaks if it's wrong:** The design's own §"Acknowledged blind spots" admits this — "If `LanguageDetection` reports a Go-only or Python-only repo, the coordinator's `for_task` filter skips them all and the YAML envelope has empty `build_system`, `manifests`, etc. slices — but the **schema requires these keys**." The recommended fix ("conditional schema branches keyed on `language_stack.primary`") is "not free — it adds schema complexity that may not pay back until Phase 7+." This is a real Phase-1 schema-validation regression on day one if a non-Node repo runs through the CLI, and the design defers it to the synthesizer.

### Things this design missed

- **The Phase 0 cache-hit pass-through (§2.6 `ProbeExecution ∈ {Ran, CacheHit, Skipped}`)** is not used anywhere in the test plan. `tests/integration/test_cache_hit_on_real_repo.py` asserts "second run produces zero `ProbeExecution.Ran` for the Phase 1 probes" — which is the only mention. The seam Phase 0 built for incremental gather (Phase 14) is being audited via a single integration test.
- **Adversarial inputs.** Zero adversarial fixtures, zero YAML/JSON bomb mitigation, zero hostile filename handling. The security lens is the load-bearing rebuttal — best-practices ignores it entirely.
- **Performance regression tests.** Wall-clock targets are listed ("Cold p50 ≤ 4s, p95 ≤ 8s") as "*targets surfaced as advisory CI dashboard metrics*, not blocking gates" — but no dashboard infrastructure is specified beyond Phase 0's PR-comment cold-start canary. The targets float free.
- **`packageManager` field vs lockfile conflict** is named ("we emit `warnings: [...]` and prefer the lockfile") but the schema treatment of `warnings: list[str]` is not constrained — strings can be anything. Best-practices doesn't propose a `warnings` enum or a schema for the warning shapes.

---

## Cross-design observations

### Where do the three disagree?

| Dimension | Performance picks | Security picks | Best-practices picks | What's at stake |
|---|---|---|---|---|
| Cache key from declared_inputs | `(path, size)` + PathIndex BLAKE3 fingerprint over packed buffer; in-process LRU above the on-disk store | BLAKE3 of *file bytes* of every input (poisoning resistance) | Phase 0's content-hash via `declared_inputs` (unchanged) | Cache poisoning resistance vs warm-path latency vs governance (Phase 0 ADR) |
| `node --version` invocation | (silent; doesn't address) | **No** — RCE surface via `$PATH` | **Yes** — read both engines.node *and* `node --version`; surface disagreement | Whether `localv2.md §5.1 A2` is conformed or partially-conformed; whether `ALLOWED_BINARIES` grows in Phase 1 |
| Inter-probe parsed-state sharing | **Yes** — msgpack cache in `ctx.workspace` (~10x faster) | (not addressed; sandbox would block) | **No** — each probe re-parses; "violates DRY by a small margin" | The cache-hit pass-through seam vs warm-path latency vs probe isolation |
| Probe execution model | One asyncio task per probe in coordinator process; PathIndex shared dataclass | One subprocess (`python -m codegenie.probes._sandbox`) per probe per gather, rlimits applied before exec | Phase 0 model unchanged (one asyncio task per probe; no subprocess) | "Extension by addition" vs hardened parser containment vs warm-path latency budget |
| `additionalProperties: false` at per-probe sub-schemas | (not specified) | **Yes** — load-bearing for Phase 1 owns | **Yes** — friction is the point | Whether Phase 1 tightens the layered policy Phase 0 §2.9 left at `additionalProperties: true` under `probes.*` |
| Hand-rolled `yarn.lock` parser | **Yes** — save 200 ms; feature-flagged with subprocess fallback | **Yes** — no regex backtracking; the only deterministic option | **Maybe** — adopt `pyarn` if maintained, fallback hand-rolled | Maintenance liability vs deterministic, capped parsing vs library-status bet |
| Native module detection scope | Catalog match on parsed deps (no version-range eval) | Catalog match; `node_modules/*/package.json` parsing **opt-in** with 1 GB aggregate cap | Catalog match on lockfile resolved packages | Coverage vs DoS surface; how confident Phase 7 distroless picks are seeded |
| Streaming write vs batch | **Yes** — slice-by-slice as probes finish; views.json sibling | (not addressed) | Phase 0 batch write (unchanged) | Peak RSS vs partial-file failure mode vs Phase 8 forward-compat |

### Which disagreement matters most for *this* phase?

**The cache-key derivation disagreement** (`(path, size)` vs file bytes vs Phase 0 default). Three reasons:

1. It rewrites a Phase 0 chokepoint (`codegenie/cache/keys.py`) and is therefore the most likely to fail the ADR-amendment governance Phase 0 §12 mandates. The synthesizer must explicitly choose whether Phase 1 changes this seam at all.
2. It is the load-bearing input to *every* subsequent decision: warm-path latency (perf), poisoning resistance (security), cache-hit-on-second-run exit criterion (best-practices/roadmap).
3. The three designs do not even share a definition of what's hashed: PathIndex packed-buffer fingerprint (perf), per-file BLAKE3 with `O_NOFOLLOW` (security), Phase 0 default with no explicit Phase-1 statement (best-practices). The synthesizer can't pick a winner without picking a shape.

The **probe execution model** is the runner-up — sandboxing every probe is a fork in the road that, once chosen, constrains the next ten phases' fork+exec budget.

### Where do all three quietly agree on something questionable?

1. **All three want per-probe `additionalProperties: false` at the sub-schema root** (perf via "views.json schema", security via Goal #9, best-practices via "the friction is the point") — *but none cite Phase 0 §2.9's layered policy as the place to extend, and none specify what happens when a forward-compatible field needs to land between Phase 1 and the synthesizer-of-the-next-phase*. Strictness ratchets up by default; loosening is what triggers an ADR amendment. None of the three designs sets a release-versioning policy for the sub-schemas.

2. **All three duck the question of `LanguageDetectionProbe`'s extension.** Perf says "Phase 0 already shipped this; I'm describing only the Layer A delta." Security says "extended from Phase 0." Best-practices says "extension, not new." Phase 0 §12 says new probes via new files; extending an existing probe in-place to add framework hints + monorepo detection is the *single most edit-by-modification* move all three designs make, and none of them argues why it's allowed.

3. **All three accept reading `package.json` more than once per gather** (perf: msgpack cache; security: each sandbox subprocess re-parses; best-practices: each probe re-parses for "isolation"). None of them uses Phase 0's `ProbeExecution.Ran(output)` as a coordinator-level cache-of-the-current-gather to share parsed state. The cheapest, cleanest seam goes untouched.

4. **All three either omit or under-specify the `warnings: list[str]` and `errors: list[str]` field shapes.** `localv2.md §4`'s `ProbeOutput` has both as `list[str]`. Free-form strings flow into the schema; downstream phases will need to parse them. None of the three lenses proposes a typed warning enum or even a regex contract.

---

## Roadmap-level critiques

1. **Does this phase, as designed across the three, set up problems for later phases?**

   Yes. Three concrete examples:
   - **Phase 2 (IndexHealthProbe).** Phase 2's whole point is that "silent index staleness is the worst failure mode." Perf's in-process LRU that skips validator re-check on hit, security's TOCTOU window between cache-key derivation and sandbox read, and best-practices' silent native-module-catalog gap are three independent silent-staleness vectors Phase 1 introduces *into the system that Phase 2's load-bearing probe will be expected to catch*. IndexHealthProbe is being set up to catch defects Phase 1 just installed.
   - **Phase 7 (Chainguard distroless migration).** Best-practices treats the native-module catalog as Phase 1's responsibility; perf doesn't address it; security treats it as a YAML edit. Phase 7's exit criterion is "the diff for this phase touches *only* new files — no Phase 0–6 source code is modified." A native module discovered in Phase 7 that requires a *new field* on the catalog forces a Phase-1-file edit, breaking the extension-by-addition test. None of the three designs version the catalog (best-practices Open Question #7 raises it; no design resolves it).
   - **Phase 8 (Hot views).** Perf pre-renders `views.json` for Phase 8 today, in Phase 1, against ADR-0013 which is deferred. If Phase 8 changes its hot-view slice list, Phase 1 follows. That's a Phase-8 → Phase-1 edit by definition.

2. **Does it rely on something an earlier phase didn't actually establish?**

   Multiple cases:
   - **Security relies on a `python -m codegenie.probes._sandbox` entry point not in Phase 0's layout** (Phase 0 §2.1 lists `probes/{base.py, registry.py, language_detection.py}` — no `_sandbox.py`). The design treats the entry as if it exists.
   - **Perf relies on Phase 0's "in-process cache" pattern** (msgpack-of-parsed-package.json) which Phase 0 never sanctioned. The design admits it: "It's not in the Phase 0 ABC and not in `localv2.md §4`."
   - **Best-practices relies on the layered `additionalProperties` policy being tightened in Phase 1 without naming whether the Phase-0 envelope schema's `probes.*: additionalProperties: true` (Phase 0 §2.9, conflict-table row 4) needs to flip.** It does — under best-practices' shape — but the design doesn't propose how the existing schema file is edited.
   - **All three rely on `ResourceBudget` / RSS enforcement that Phase 0 deferred to "advisory" tracking.** Perf names this; security and best-practices implicitly assume it. Phase 0 didn't ratify hard enforcement.

3. **Does it violate any load-bearing commitment from `production/design.md §2` or `CLAUDE.md`?**

   Yes, by lens:

   - **Perf** violates §2.5 (Extension by addition) twice — (a) the `PathIndex` mixin is a *new class hierarchy alongside* `Probe`, which is editing-by-parallel; (b) `views.json` projection edits the Phase 0 writer's pass model (one batch → streaming + sibling). It violates §2.3 (Honest confidence) by skipping LRU revalidation on the hot path. It violates the `localv2.md`-is-source rule (Phase 0 §2.3) by introducing `PathIndex` enrichment that probes opt into "without changing the Phase 0 ABC" but which only works if the coordinator and the probes share knowledge of the mixin — i.e., the ABC's effective contract has changed.

   - **Security** violates §2.5 (Extension by addition) by adding a third pass to `OutputSanitizer.scrub` (a frozen Phase-0 chokepoint) without proposing an ADR amendment. It violates Phase 0 §2.7's frozen Cache API by changing what's hashed in `key_for`. It violates Rule 11 (Match the codebase's conventions) by unilaterally vetoing `node --version` against `localv2.md §5.1 A2` and proposing "argued explicitly because `localv2.md` is the contract" — the framing inverts conformance. The macOS sandbox gap means Goal #1 ("Zero successful parse-driven RCE") is platform-conditional, which is Rule 12 (fail loud) failing quietly.

   - **Best-practices** violates Rule 11 (conformance > taste) by treating the `localv2.md §5.1 A4` singleton-vs-list shape as "a doc-update candidate" — Phase 0 §2.3 says "Resolution policy in the ADR amendment: `localv2.md` is the source of truth; the implementation must conform." It violates Rule 9 (Tests verify intent) by ratcheting coverage to 90/80 and then carving out `deployment.py` to 85% — coverage as theater. It risks `production/design.md §2.3` (Honest confidence) by relying on Phase 7's integration tests to catch native-module-catalog gaps five phases out.

   - **All three** quietly leave the `warnings: list[str]` field shape unconstrained, which `production/design.md §2.2` (Facts, not judgments) makes load-bearing: warnings are facts about the probe run, and free-form strings *are* the channel through which a probe author smuggles judgments back in. The structural defense (typed warning shapes) is absent across the board.
