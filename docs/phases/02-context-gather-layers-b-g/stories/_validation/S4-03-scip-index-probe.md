# Validation report — S4-03 (`ScipIndexProbe` + `grammars.lock` infrastructure)

**Story:** [S4-03-scip-index-probe.md](../S4-03-scip-index-probe.md)
**Date:** 2026-05-16
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's intent is right — produce the `.scip` semantic index, emit the `semantic_index`
slice B2 reads (indirectly), and land the `grammars.lock` infrastructure that S4-04
consumes. The architectural framing (Phase 2 emits only; Phase 3 adapts; freshness via
typed `IndexerError`; tool-version + `.ts` Merkle as cache-key sensitivities) is
consistent with `phase-arch-design.md §"Edge cases" row 4`, ADR-0002, and S4-01's
hardened B2 contract.

But seven BLOCK-severity inconsistencies with master would crash the executor's first
red-test pass:

1. The probe is spec'd to write only the `.scip` binary blob — **but B2 reads a JSON
   sibling at `<output_dir>/raw/scip.json`** (per S4-01 hardened, cross-story hand-off
   commitment). The story does not produce that file. Without it, B2 fires
   `Stale(IndexerError("upstream_scip_unavailable"))` on every gather, even when the
   index is genuinely fresh.
2. `Probe.run` is two-arg `(self, repo: RepoSnapshot, ctx: ProbeContext)`; impl outline
   prescribes one-arg `(self, ctx)`.
3. `run_external_cli` raises `ProbeTimeoutError`, not `asyncio.TimeoutError`; AC-6 +
   T-07 use the wrong type.
4. `run_external_cli` raises `ToolMissingError` for binary-missing, not
   `FileNotFoundError`; AC-8 uses the wrong type.
5. `ProcessResult` is `(returncode: int, stdout: bytes, stderr: bytes)` —
   no `exit_code`, no `stderr_tail`; AC-3, AC-7, T-08 use the wrong attribute names.
6. `run_allowlisted` does not raise `CalledProcessError`; non-zero exit returns
   `result.returncode != 0`. Impl outline 3.2 handles a phantom exception.
7. The declared-input token `scip-typescript-version:<resolved>` (AC-2) is silently
   dropped by master's `cache/keys.py::declared_inputs_for` — the function does
   `rglob` only; no token dispatch is implemented. ADR-0004 prescribed the mechanism
   for `image-digest:`, but S1-09 (Done) only added the `ProbeContext.image_digest_resolver`
   field; the cache-layer token recognizer was deferred. And `_OUTPUT_NAMESPACE = ".codegenie"`
   strips anything under that namespace. So the central tool-version cache-key
   invariant (T-06) is unverifiable on master without further work.

Plus ten HARDEN-severity weaknesses (most consequential: `files_in_repo` vs
`files_indexed` glob-set mismatch silently fires `CoverageGap` on healthy
indexes; no AC pinning `scip.json` field-name byte-equivalence with B2's
reader; subprocess at import time; missing warm-cache hand-off AC).

And four design-pattern opportunities that elevate kernel extraction
candidates **at the rule-of-three threshold** — tool-version memoization is
about to be repeated in five Phase-2 probes; the slice shape is about to be
written in two places without a typed boundary; the `grammars.lock`
reader/verifier will be needed in S4-04 too; and the special-token gap has
a simpler, smaller-blast-radius escape hatch (bake the tool version into
`probe.version` — already in the cache key per `cache/keys.py:146`).

After hardening, every AC is verifiable against the master surface, the
hand-off to B2 (S4-01 hardened) is mechanically guaranteed, and the
extension-by-addition stance for Phase-3 tools is preserved.

## Context Brief

**What the story promises:**

1. `ScipIndexProbe` invokes `scip-typescript` via `run_external_cli`, emits a
   `.scip` binary blob to `<raw>/scip-index.scip`, and emits a `semantic_index`
   slice in `repo-context.yaml` with the metadata B2's `scip_freshness` check
   reads.
2. Cache-key sensitivity: tool-version AND `.ts`-Merkle both invalidate.
3. Timeout (300s budget per phase-arch row 4) → typed `IndexerError(message="timeout")`
   in the slice; B2 emits `Stale`; no exception escapes.
4. `tools/grammars.lock` + `tools/regenerate_grammars_lock.sh` + vendored grammar
   binaries land here (consumer is S4-04 — bundling lock + first-need is a
   deliberate dependency-closure choice).

**What the phase's exit criteria demand:**

- Layer B must emit semantic-index evidence B2 can read (`phase-arch-design.md
  §"Component design" #1` — B2 is the load-bearing citizen; SCIP is its primary
  source).
- `scip-typescript` timeout MUST become `IndexFreshness.Stale(IndexerError("timeout"))`,
  not a crash (`phase-arch-design.md §"Edge cases" row 4`).
- `tools/grammars.lock` is the supply-chain defense for `tree-sitter` (ADR-0002).
- Adding a new probe must require zero edits to existing probe code (CLAUDE.md
  "Extension by addition").

**What the arch + ADRs constrain:**

- **Probe ABC** (`src/codegenie/probes/base.py:74-94`): `async def run(self, repo:
  RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. Two-arg. `ProbeOutput` has
  `raw_artifacts: list[Path]` (not the writer's `list[tuple[str, bytes]]`).
  `ProbeContext` has `output_dir` (where probe writes raw artifacts), `workspace`,
  `cache_dir`, `parsed_manifest`, `input_snapshot`, `image_digest_resolver`. NO
  `sibling_slices`. NO `snapshot.root` access via `ctx` — `repo` is the first
  argument; `repo.root` is the path.
- **`exec.py`** (`src/codegenie/exec.py:140-150, 216-352, 485-600`):
  - `ProcessResult(returncode: int, stdout: bytes, stderr: bytes)`. Frozen
    dataclass. No `exit_code`. No `stderr_tail`. Stderr is `bytes` — caller
    decodes and tails.
  - `run_allowlisted` raises `ToolMissingError`, `ProbeTimeoutError`,
    `DisallowedSubprocessError`, `FileNotFoundError`, `NotADirectoryError`.
    Non-zero exit returns the `ProcessResult` with `returncode != 0`.
  - `run_external_cli` wraps `run_allowlisted`; same taxonomy. Output
    truncation at 64 MB returns a new `ProcessResult` with possibly
    truncated stdout/stderr — the call site must not assume bytes
    completeness; it has the `truncated` log signal in structlog.
- **`cache/keys.py`** (`src/codegenie/cache/keys.py:94-126, 129-148`):
  `declared_inputs_for(probe, snapshot) -> list[Path]` resolves each declared
  input via `snapshot.root.rglob(pattern)`, filters paths under
  `.codegenie/`, sorts, returns. **There is no special-token dispatch.**
  `key_for` hashes `(probe.name, probe.version, per_probe_schema_version(probe),
  content_hash_of_inputs(declared_inputs_for(...)))`. `probe.version` IS in the
  cache key — that is the escape hatch DP4 names below.
- **S4-01 hardened**, AC-12 + impl outline §2 + §5: B2's `read_raw_slices(raw_dir)`
  reads every `<index_name>.json` under `<repo>/.codegenie/context/raw/`. For
  `IndexName("scip")` the file is **`scip.json`**. The slice content must
  contain the keys B2's `scip_freshness` reads: `last_indexed_commit`,
  `files_indexed`, `files_in_repo`, `indexer_errors`, `last_indexed_at`. The
  cross-story hand-off commitment is explicit: "S4-03 (SCIP), S5-05
  (runtime_trace), S6-08 (semgrep/gitleaks/conventions) MUST each write a
  `<index_name>.json` raw artifact under that directory during their `run()`."
- **`output/writer.py:142-184`**: the writer takes
  `raw_artifacts: list[tuple[str, bytes]]` from the coordinator (the probe-side
  `ProbeOutput.raw_artifacts: list[Path]` is converted by the coordinator into
  the writer's input — this story's probe ships file paths under `ctx.output_dir`,
  and the coordinator/writer handle the final write).
- **CLAUDE.md** "Extension by addition" + Rule 2 "Simplicity First" + Rule 11
  "Match the codebase's conventions" all bear on this story.

## Source-of-truth verifications (grep against master + sibling stories)

| Reference in draft | Master surface | Verdict |
|---|---|---|
| Impl outline §3: `async def run(self, ctx) -> ProbeOutput` | `Probe.run(self, repo: RepoSnapshot, ctx: ProbeContext)` at `src/codegenie/probes/base.py:94` | **PHANTOM** — one-arg signature would `TypeError` at dispatch |
| AC-6 / T-07: `run_external_cli` "raises `asyncio.TimeoutError`" | `src/codegenie/exec.py:338` raises `ProbeTimeoutError` | **PHANTOM** — wrong exception type; test would never trigger the real path |
| AC-8 / T-10: `run_external_cli` "raises `FileNotFoundError`" for binary-missing | `src/codegenie/exec.py:320` raises `ToolMissingError`; `FileNotFoundError` only for cwd missing | **PHANTOM** — wrong taxonomy |
| AC-3 / AC-7 / T-08: `ProcessResult(exit_code=…, stderr_tail=…)` | `src/codegenie/exec.py:140-150` — `returncode: int, stdout: bytes, stderr: bytes` (frozen) | **PHANTOM** — both attribute names + the `stderr_tail` field are wrong; `stderr` is `bytes` so caller decodes + tails |
| Impl outline §3.2: handle `CalledProcessError` from `run_allowlisted(["git", "rev-parse", "HEAD"], ...)` | `run_allowlisted` returns `ProcessResult` with `returncode != 0`; does NOT raise `CalledProcessError` (per `src/codegenie/exec.py:216-355` and `S4-01` hardened §5) | **PHANTOM** — caller must inspect `result.returncode`, not catch `CalledProcessError` |
| AC-2 + T-06: declared-input token `scip-typescript-version:<resolved>` | `src/codegenie/cache/keys.py:94-126` — `declared_inputs_for` is rglob-only, no token recognizer; `_OUTPUT_NAMESPACE = ".codegenie"` filters `.codegenie/*` paths. ADR-0004's token mechanism is referenced but unimplemented (S1-09 added only the `ProbeContext.image_digest_resolver` field, not the `Cache._resolve_declared_inputs` token dispatch) | **PHANTOM** — the token is silently dropped on master; cache key is invariant to `scip-typescript` upgrades; T-06 would not catch the regression |
| AC-4 + T-04: blob path `<snapshot.root>/.codegenie/context/raw/scip-index.scip` | `output/paths.py:20` `raw_dir(repo_root) -> repo_root / ".codegenie/context/raw"`; probe writes via `ProbeContext.output_dir` per ABC (`base.py:53` "where probe writes raw artifacts"). The two paths normally coincide but the contract is `ctx.output_dir`, not `repo.root` | **INCONSISTENT** — adapt to `ctx.output_dir / "raw" / "scip-index.scip"`; matches Phase 1 convention |
| AC-13: import-time `assert ...` on `_WARNING_IDS` | Phase 0 forbidden-patterns hook bans bare `assert` in `src/codegenie/` (see `scripts/check_forbidden_patterns.py`). Module-level validation must use `raise RuntimeError(...)` or be a unit test | **CONVENTION-DRIFT** — use unit test (precedent: S4-01's `_WARNING_IDS` is verified by a test, not import-time assert) |
| AC-5 `files_indexed` parsed from `--summary-json` vs `files_in_repo` walks `.ts/.tsx/.js/.jsx` | `localv2.md §5.2 B1 line 567`: "scip-typescript … reads `tsconfig.json`, runs the TypeScript compiler API". `.js`/`.jsx` outside the TS program are covered by `TreeSitterImportGraphProbe` (S4-04), NOT by `scip-typescript`. So `files_indexed` (TS scope) < `files_in_repo` (TS+JS scope) on any healthy mixed repo | **SEMANTIC GAP** — B2's `scip_freshness` AC-5(d) fires `Stale(CoverageGap)` on every healthy mixed JS+TS repo. Fix: restrict `files_in_repo` to `.ts/.tsx` only (the scip-typescript program scope); `.js/.jsx` coverage is a `TreeSitterImportGraphProbe` (S4-04) concern |
| AC-5 + (missing): no AC for `<raw>/scip.json` | S4-01 hardened cross-story commitment (line 13 of S4-01): "Cross-story handoff: S4-03 (SCIP), S5-05 (runtime_trace), S6-08 (semgrep/gitleaks/conventions) MUST each write a `<index_name>.json` raw artifact under that directory during their `run()`." S4-01 AC-12 (sibling-missing) expects `Stale(IndexerError("upstream_scip_unavailable"))` ONLY when the file is absent — i.e., a healthy SCIP probe must write the file | **LOAD-BEARING MISSING REQUIREMENT** — without `scip.json`, B2 fires `Stale(IndexerError("upstream_scip_unavailable"))` on every gather, defeating the whole `index_health` slice. New AC must mandate writing it |

## Critic reports

### Coverage critic — BLOCK + HARDEN

**F-Cov-1 (BLOCK).** Missing the load-bearing `<raw>/scip.json` artifact. Without
it, B2 sees an absent sibling on every gather. S4-01 hardened explicitly demands
this cross-story hand-off. New AC required: AC-Sj — write the slice as JSON to
`<output_dir>/raw/scip.json` so that B2's `read_raw_slices(raw_dir)` reads it as
the `IndexName("scip")` sibling slice. The JSON content's keys must be exactly
the keys B2's `scip_freshness` reads (`last_indexed_commit`, `files_indexed`,
`files_in_repo`, `indexer_errors`, `last_indexed_at`).

**F-Cov-2 (HARDEN).** `files_in_repo` glob set is wider than `files_indexed`
scope. `.js/.jsx` are scip-typescript-invisible (per `localv2.md §5.2 B1`).
Restrict `files_in_repo` to `.ts/.tsx`; document that `.js/.jsx` coverage is a
S4-04 `TreeSitterImportGraphProbe` concern; B2's CoverageGap then reflects a real
gap. Adjust AC-5, AC-9, T-09.

**F-Cov-3 (HARDEN).** No AC pinning warm-cache hand-off — if the probe cache-HITs
(unchanged inputs), the coordinator replays the prior `ProbeOutput.raw_artifacts`
list; `scip.json` must be in that list so B2 still reads it. Add AC explicitly
declaring `scip.json` is a `raw_artifacts` member (not just a side-effect-write).

**F-Cov-4 (HARDEN).** Edge case missing: empty repo (no `.ts`/`.tsx` files at
all). `coverage_pct=0.0` per AC-5, but B2's `scip_freshness` AC-5(b) requires
`files_indexed == files_in_repo` AND `indexer_errors == 0` for `Fresh`. On an
empty repo, `0 == 0` triggers `Fresh` — but `last_indexed_at` must still be a
valid ISO timestamp B2 can parse. T-XX: empty-repo case asserts `Fresh` outcome
on B2.

**F-Cov-5 (HARDEN).** Edge case missing: monorepo with multiple `tsconfig.json`
projects. `scip-typescript --infer-tsconfig` picks one or surfaces all — the
behavior under multi-project repos is undocumented in the story. Either declare
it scope (and the multi-project case is S4-04 / S7-05) or add an AC for the
fallback.

**F-Cov-6 (HARDEN).** AC-5's `coverage_pct = files_indexed / files_in_repo * 100`
needs explicit zero-handling: `files_in_repo == 0` → `0.0` AND `confidence="low"`.
Story has this in AC-5 — but does not flow to B2's check. B2 sees `files_indexed
== files_in_repo == 0` → AC-5(b) `Fresh`. The two layers disagree on the
empty-repo's confidence. Either align (probe emits `Fresh` slice + `confidence="low"`
locally + B2 sees `Fresh`) or carve out a B2 rule. Document the agreement.

### Consistency critic — BLOCK

**F-Con-1 (BLOCK).** Probe-run signature: ABC has `(self, repo: RepoSnapshot,
ctx: ProbeContext)`. Impl outline §3 uses `(self, ctx)`. Fix throughout.

**F-Con-2 (BLOCK).** Timeout exception is `ProbeTimeoutError`, not
`asyncio.TimeoutError`. AC-6 + T-07 must use `ProbeTimeoutError` (from
`codegenie.errors`).

**F-Con-3 (BLOCK).** `ProcessResult` shape: `returncode: int, stdout: bytes,
stderr: bytes`. Frozen. AC-3/AC-7/T-08 must use these names. `stderr_tail` is
caller-derived: `result.stderr[-4096:].decode("utf-8", errors="replace")`.

**F-Con-4 (BLOCK).** Tool-missing exception is `ToolMissingError`, not
`FileNotFoundError`. AC-8 + T-10 fix.

**F-Con-5 (BLOCK).** Impl outline §3.2 catches `CalledProcessError` from
`run_allowlisted` for `git rev-parse HEAD`. `run_allowlisted` returns
`ProcessResult` with `returncode != 0`; does not raise `CalledProcessError`.
Fix to: check `result.returncode != 0`.

**F-Con-6 (BLOCK).** AC-2's `scip-typescript-version:<resolved>` declared-input
token has no master support. `cache/keys.py::declared_inputs_for` does
`snapshot.root.rglob(pattern)` only; no token dispatch is implemented; ADR-0004
prescribed it for `image-digest:` but S1-09 (Done) only added the
`ProbeContext.image_digest_resolver` field. Pivot to DP4 (bake tool version into
`probe.version`) — already in cache key per `cache/keys.py:146`. No new ADR;
no new mechanism; immediately verifiable.

**F-Con-7 (HARDEN).** AC-13 import-time `assert` on `_WARNING_IDS` will trip
Phase 0 forbidden-patterns ban on bare `assert` in `src/codegenie/`. Convert to
unit test (precedent: S4-01).

**F-Con-8 (HARDEN).** AC-4's path `<snapshot.root>/.codegenie/context/raw/...`
conflates two contracts — `repo.root` (the analyzed repo) and `ctx.output_dir`
(where the probe is told to write artifacts). Use `ctx.output_dir / "raw" /
"scip-index.scip"` per `ProbeContext.output_dir` docstring; the slice's
`scip_index_uri` is the path relative to `repo.root` for the renderer.

### Test-quality critic — HARDEN

**F-TQ-1 (HARDEN).** T-06 (cache-key sensitivity) as written would silently PASS
on master: `scip-typescript-version:<resolved>` is dropped by `declared_inputs_for`,
so both arms produce identical `key_for(...)` output. Rewrite T-06 to assert
against the chosen DP4 mechanism: bumping `probe.version` (the literal class
attribute) changes the key.

**F-TQ-2 (HARDEN).** T-07 (timeout) raises `asyncio.TimeoutError`; would not
exercise the real `ProbeTimeoutError` path; would PASS for the wrong reason. Fix
to `ProbeTimeoutError`.

**F-TQ-3 (HARDEN).** T-08 (non-zero exit) constructs `ProcessResult(exit_code=2,
stderr_tail=…)`; won't even compile against master. Fix to `ProcessResult(
returncode=2, stdout=b"", stderr=b"bad tsconfig\n")` and assert the probe derives
the tail string via `result.stderr[-4096:].decode("utf-8", errors="replace")`.

**F-TQ-4 (HARDEN).** T-09 references `_compute_indexable_merkle` — not in the
helper list in impl outline §1. Add to the helper list (a fourth pure helper)
and to T-09's import; assert merkle-and-count share one walker (test the
exclusion symmetry by adding a `node_modules/extra.ts` and asserting BOTH the
count and the merkle ignore it).

**F-TQ-5 (HARDEN).** T-04 uses a stub that "writes a known byte string to
`--output`" — under-specified. Provide the exact stub shape:

```python
async def _stub_writes_blob(probe_id, argv, *, cwd, timeout_s, max_stdout_bytes=...):
    out_path = Path(argv[argv.index("--output") + 1])
    out_path.write_bytes(b"FAKE-SCIP-BLOB")
    return ProcessResult(returncode=0, stdout=b'{"files_indexed":1}', stderr=b"")
```

**F-TQ-6 (HARDEN).** No mutation-killer for `scip.json` field-name shape.
Add T-Sj-1: write a real slice via probe `run()`; load JSON from
`<output_dir>/raw/scip.json`; assert the key-set is exactly the B2-required
subset (no rename, no drop). Closes the cross-story hand-off invariant by
test, not by hope.

**F-TQ-7 (HARDEN).** No metamorphic/property test for monotonicity. Property:
for a given input set, two consecutive `run()` invocations (clean cache, same
inputs) produce identical slice contents modulo `last_indexed_at`. Useful
mutation-killer for any future "sort symbols by hashable order" regression.

**F-TQ-8 (NIT).** AC-6 step 4's hardcoded f-string
`f"indexer_reported_1_errors"` is consumer-coupled to S4-01's `scip_freshness`
AC-5(e). T-07 should assert via constructing the B2 freshness check directly
(or via a small fixture exposing the expected key shape) rather than encoding
the f-string twice. Closes a silent break if S4-01's message string is
refactored.

### Design-patterns critic — HARDEN (kernel-extraction opportunities)

**F-DP-1 (HARDEN).** Tool-version resolution is about to be repeated in five
Phase-2 probes (`scip-typescript`, `tree-sitter`, `grype`, `syft`, `semgrep`,
`gitleaks`). Third+ concrete consumer of a family — rule-of-three threshold
crossed. Recommend: extract `codegenie.exec.tool_versions.resolve_tool_version(
binary: str) -> str` with a process-wide memo + `clear_for_tests()` (mirror
`unregister_for_tests` pattern from S1-02 freshness registry). Composes with
F-Con-7 (`_WARNING_IDS`-style import-time work moves out of the probe).
**Story AC** (added as an extension-by-addition AC, not a pattern-name AC):
"Adding a new external-CLI probe must require zero edits to `scip_index.py` for
tool-version resolution — the tool-version resolver is a shared module-level
helper, not a probe-private memo." Verified by structural test: grep the new
probe's module; no module-level subprocess call.

**F-DP-2 (HARDEN).** `SemanticIndexSlice` typed boundary (smart constructor).
The slice fields are emitted at two places now (the `repo-context.yaml`
envelope AND `<raw>/scip.json`). Extract a Pydantic model:

```python
class SemanticIndexSlice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scip_index_uri: str
    indexer: Literal["scip-typescript"]
    indexer_version: str
    files_indexed: int = Field(ge=0)
    files_in_repo: int = Field(ge=0)
    coverage_pct: float = Field(ge=0.0, le=100.0)
    last_indexed_commit: str
    last_indexed_at: str
    indexer_errors: int = Field(ge=0)
    indexer_warnings: int = Field(ge=0)
    # Optional summary-json fields:
    any_type_density: float | None = None
    unresolved_dynamic_imports: int | None = None
    unresolved_computed_access: int | None = None
    symbol_count: int | None = None
    exported_symbols: int | None = None
```

The probe builds the model once and serializes to both targets via
`model_dump(mode="json", exclude_none=True)`. Closes F-TQ-6 by construction:
the JSON sibling and the envelope slice are the same model. Mirrors S3-02's
`RedactedSlice` smart-constructor pattern. **Story note** (not AC): use the
model; document the key invariant under "Notes for implementer."

**F-DP-3 (HARDEN).** `tools/grammars.lock` reader/verifier should land as a
small typed module `codegenie.grammars.lock`, not as ad-hoc test code. S4-04's
`TreeSitterImportGraphProbe` will need it too (pre-load BLAKE3 verification per
phase-arch row 10 `GrammarLoadRefused`). Two consumers in two adjacent stories
crosses the rule-of-three when counting the regen script — extract now to avoid
divergent verification logic.

```python
# src/codegenie/grammars/lock.py
class GrammarPin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    language: str
    version: str
    file: str          # repo-relative path
    blake3: str        # 64 hex chars

class GrammarLockFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    grammars: list[GrammarPin]

def load_and_verify(repo_root: Path) -> GrammarLockFile: ...
class GrammarLoadRefused(RuntimeError): ...
```

S4-04 imports `load_and_verify` and consumes the typed result. **Story AC**:
"`tools/grammars.lock` is parsed via `codegenie.grammars.lock.load_and_verify`
and BLAKE3 mismatches raise `GrammarLoadRefused`. A unit test exercises both
the happy path and the mismatch path."

**F-DP-4 (HARDEN — SUPERSEDES F-Con-6's pivot recommendation).** The
special-token cache-key gap (F-Con-6) has a smaller-blast-radius escape hatch
than amending the cache layer: **bake the resolved tool version into
`probe.version` itself**. `key_for` (`cache/keys.py:142-146`) hashes
`(probe.name, probe.version, per_probe_schema_version(probe),
content_hash_of_inputs(declared_inputs_for(...)))` — `probe.version` is in
the tuple. If `ScipIndexProbe.version` is, for example,
`f"0.1.0+scip-typescript-{resolve_tool_version('scip-typescript')}"`, then
a `scip-typescript` upgrade automatically invalidates the cache without any
new mechanism. Caveats:

  - `probe.version` is read via the `_ProbeLike` Protocol; making it a class
    attribute that depends on a subprocess at import time is the F-Con-7
    anti-pattern. Make it a `@property` on the probe class instead, which is
    consistent with `_ProbeLike` (a Protocol — attribute or property is
    acceptable as long as it returns `str`). The `tool_versions` module-level
    memo (F-DP-1) ensures the subprocess fires once per process, lazily.

  - The `version` string format `"0.1.0+scip-typescript-1.2.3"` is the standard
    PEP 440 "local-version" suffix — unambiguous, parseable, and survives
    sorted-cache-prune. Tests pin the format by regex (not by string equality)
    so the resolved suffix can vary.

  - Pattern: **Smart attribute + process-wide memo** — `probe.version` is
    the existing chokepoint; we route an additional signal through it instead
    of inventing a parallel chokepoint. Closes F-Con-6 + F-TQ-1 with zero new
    code in `cache/keys.py`. **Story rewrite**: AC-2 rewritten around this
    mechanism.

## Conflict resolution

- **F-DP-4 supersedes F-Con-6's pivot recommendation.** `version`-as-property
  is the simpler, smaller-blast-radius escape hatch than amending the cache
  layer to recognize `<name>:<value>` tokens. Both are real options; F-DP-4
  wins on Rule 2 (simplicity first) and Rule 3 (surgical changes).

- **F-Cov-2 (restrict `files_in_repo` to `.ts/.tsx`) wins over the original
  story's `.ts/.tsx/.js/.jsx` walk.** `scip-typescript`'s program scope is the
  source of truth; B2's CoverageGap must reflect a real gap. `.js/.jsx`
  coverage is S4-04's `TreeSitterImportGraphProbe` concern, NOT `ScipIndexProbe`'s.

- **F-Cov-4 (empty-repo path) and F-Cov-6 (zero-divisor + confidence)
  reconciled**: empty repo → slice is emitted with `files_indexed = files_in_repo
  = 0`, `coverage_pct = 0.0`, `indexer_errors = 0`, `confidence = "low"` on the
  probe envelope. B2's `scip_freshness` reads `0 == 0` and emits `Fresh(...)`.
  The two layers disagree intentionally: probe-side confidence reflects "the
  index is not informative" (zero files); B2-side freshness reflects "the
  index matches HEAD." Document the agreement in "Notes for implementer."

## Research (Stage 3) — none

No findings tagged `NEEDS RESEARCH`. All fixes are routine consistency edits or
extract-kernel design moves with clear in-repo precedent (`SecretRedactor` /
`RedactedSlice` for smart constructors; `unregister_for_tests` for the
process-wide memo with clear-for-tests seam; `register_*` decorators for
extension-by-addition).

## Edits applied (HARDENED verdict)

1. **AC-1** unchanged in structure; clarified ABC alignment.
2. **AC-2** rewritten around DP4: tool version baked into `probe.version` via
   `@property`; declared-input token form removed. `.ts/.tsx/tsconfig.json` glob
   set retained (filesystem inputs that DO survive `declared_inputs_for`).
3. **AC-3** corrected `ProcessResult` attribute names; clarified the stub
   contract per F-TQ-5; removed `asyncio.TimeoutError` mention.
4. **AC-4** rewritten to use `ctx.output_dir / "raw" / "scip-index.scip"`;
   `scip_index_uri` in the slice is the repo-root-relative form.
5. **AC-5** restricted `files_in_repo` to `.ts/.tsx`; documented the agreement
   with B2 on empty-repo + non-zero-error cases; added explicit serialization
   shape (Pydantic-derived).
6. **AC-6** corrected to `ProbeTimeoutError`; specified the
   `f"indexer_reported_{n}_errors"` hand-off explicitly with a structural
   reference to S4-01 AC-5(e).
7. **AC-7** corrected `ProcessResult` shape; clarified the `stderr_tail`
   derivation; removed `exit_code` + `stderr_tail` field references.
8. **AC-8** corrected to `ToolMissingError`.
9. **AC-9** restricted to `.ts/.tsx`; added symmetric exclusion proof in
   T-09; added `_compute_indexable_merkle` helper declaration.
10. **AC-10 / AC-11 / AC-12** unchanged in intent; clarified DP3 hand-off to
    `codegenie.grammars.lock` typed loader; AC-12 explicitly carves out
    "binary content is implementer-time work" + reviewer protocol.
11. **AC-13** converted import-time `assert` to a unit test (F-Con-7).
12. **AC-14** unchanged.
13. **AC-15** unchanged.
14. **NEW AC-16 (B2 hand-off — F-Cov-1).** `<output_dir>/raw/scip.json`
    contains a JSON object with the keys B2's `scip_freshness` reads. Verified
    by both a structural test AND an integration test that feeds the JSON
    through S4-01's `scip_freshness` check directly.
15. **NEW AC-17 (warm-cache hand-off — F-Cov-3).** `scip.json` is in the
    probe's `ProbeOutput.raw_artifacts` so warm-cache replay re-publishes it.
16. **NEW AC-18 (typed boundary — F-DP-2).** `SemanticIndexSlice` Pydantic
    model is the single source of truth for the slice shape; both the envelope
    and `scip.json` derive from `model_dump(mode="json", exclude_none=True)`.
17. **NEW AC-19 (extension-by-addition for tool versions — F-DP-1).**
    `codegenie.exec.tool_versions` houses the process-wide tool-version cache;
    the probe imports and calls it, no module-level subprocess in
    `scip_index.py`.
18. **NEW AC-20 (typed grammars-lock loader — F-DP-3).**
    `codegenie.grammars.lock` exports `load_and_verify` + `GrammarLoadRefused`;
    S4-04 imports the same.
19. **Implementation outline** corrected: `run(self, repo, ctx)`; tool-version
    resolution lazy via `tool_versions` module; `ProcessResult.returncode`
    everywhere.
20. **TDD plan** edits: T-04 stub spelled out; T-06 retargeted to
    `probe.version` mutation; T-07 + T-10 use the right exceptions; T-08 uses
    the right `ProcessResult`; new T-19 (`scip.json` field shape +
    integration with B2's `scip_freshness`); new T-20 (`tool_versions`
    process-wide memo verified by two consecutive probe-instance invocations
    triggering the subprocess exactly once); new T-21 (`grammars.lock`
    typed loader + mismatch path).
21. **Notes for implementer** appended with: the DP4 rationale; the
    `tool_versions` extraction; the `SemanticIndexSlice` smart-constructor
    rationale; the `grammars.lock` typed loader rationale; the empty-repo
    layer-disagreement note; the consumer-coupling note for S4-01's
    `f"indexer_reported_{n}_errors"` (use S4-01's published constant rather
    than re-encoding).

## Verdict: **HARDENED**

Story's intent matches the phase exit criteria. Seven BLOCK-severity phantoms
closed; ten HARDEN-severity weaknesses closed; four design-pattern
opportunities elevated to load-bearing ACs (DP1, DP2, DP3, DP4). After
hardening, every AC is verifiable against master, the cross-story hand-off
to B2 is mechanically guaranteed, and the extension-by-addition stance for
Phase-3 tools (Python/Java/Go via additional `tool_versions`-registering
probes) is preserved.
