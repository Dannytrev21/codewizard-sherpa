# Validation report — S4-02 (`stale-scip` fixture stub + load-bearing adversarial test)

**Story:** [S4-02-stale-scip-adversarial.md](../S4-02-stale-scip-adversarial.md)
**Date:** 2026-05-16
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's intent is correct — encode the Phase 2 roadmap exit criterion as a CI-gating
adversarial test asserting `Stale(reason=CommitsBehind(n>=1, last_indexed!=HEAD))` from
`IndexHealthProbe` against a deliberately-seeded fixture. The structural assertion (both
inequalities, implementation risk #3) is well-articulated and ports cleanly from
`High-level-impl.md §"Risks specific to this step"`. However the *prescriptions* drift
from S4-01's hardened surface in six load-bearing ways, contradict repo-wide
`.gitignore` realities in one mechanical way, and miss one design-pattern opportunity
that the next four adversarial stories in `tests/adv/phase02/` will inherit.

Seven BLOCK-severity findings closed; eight harden findings closed; four design-pattern
notes added. After hardening, the executor can take this story to GREEN without
hitting a phantom surface on its first tool call.

## Context Brief

**What the story promises:**
1. `tests/adv/phase02/test_stale_scip_fixture.py` invokes `IndexHealthProbe` against
   `tests/fixtures/portfolio/stale-scip/` and asserts the typed structural outcome:
   `isinstance(freshness, Stale)` AND `isinstance(freshness.reason, CommitsBehind)`
   AND `n >= 1` AND `last_indexed != current_HEAD`.
2. A stub fixture lands in this story — directory, regenerate script with explicit
   refuse-retarget guard, README documenting the regeneration policy, minimal seed
   material; the full materialization (real `scip-typescript` blob) is S7-02.
3. The pytest marker `phase02_adv` is registered so `pytest -m phase02_adv` selects
   this test; S8-03 lands the `adv-phase02` CI job YAML that consumes the marker.
4. The test is build-gating — no `pytest.skip` path, loud failure with
   `model_dump_json(indent=2)` diagnostics on regression.

**What the phase's exit criteria demand:**
- [`phase-arch-design.md §"Goals" G2`](../../phase-arch-design.md) — "Build FAILS if
  the probe does not catch it. This is the roadmap exit criterion."
- [`phase-arch-design.md §"Process view" Scenario 2`](../../phase-arch-design.md) —
  the sequence diagram pins the exact assertion shape.
- [`High-level-impl.md §"Risks specific to this step" #3`](../../High-level-impl.md)
  — *both* `CommitsBehind.n >= 1` AND `last_indexed != current_HEAD` are asserted
  (the second inequality is the falsifier against the AC-6 `n=1` fallback path).

**What the arch + ADRs constrain:**
- 02-ADR-0006 — `IndexFreshness` is the discriminated union with `kind` discriminator;
  `Stale.reason` carries the typed `CommitsBehind(n, last_indexed)` variant.
- Phase 0 ADR-0007 — `Probe.run(self, repo, ctx)` is **two-argument**; `ProbeContext`
  has `cache_dir, output_dir, workspace, logger, config, parsed_manifest,
  input_snapshot, image_digest_resolver` — **no** `sibling_slices` field.
- S4-01 (hardened) — B2 reads sibling slice data from `<repo>/.codegenie/context/raw/
  <index_name>.json` via the pure helper `read_raw_slices(raw_dir)`; the file for
  `IndexName("scip")` is named **`scip.json`** (keyed by stem).
- S4-01 (hardened) — the freshness registry exposes `unregister_for_tests(index_name)`
  (per-name) and `registered_names()`; no global `_clear_for_tests()` exists. Tests
  use a snapshot-and-restore fixture (S4-01's `clean_freshness_registry`).
- Repo-wide `.gitignore` ignores `.codegenie/` everywhere — fixtures cannot commit
  `.codegenie/context/raw/scip.json` directly; the seed material must live at a
  tracked path and `regenerate.sh` must copy it into the gitignored runtime location.

## Source-of-truth verifications (grep against master + sibling stories)

| Reference in draft | Master surface | Verdict |
|---|---|---|
| `asyncio.run(probe.run(ctx))` (line 176) — one-arg | `Probe.run(self, repo: RepoSnapshot, ctx: ProbeContext)` at `src/codegenie/probes/base.py:94`; two-arg per Phase 0 ADR-0007 + S4-01 hardened AC-1 | **PHANTOM** — would `TypeError` immediately |
| `build_probe_context(snapshot_root=FIXTURE, sibling_slices={"scip": sibling})` (line 173) | `tests/helpers/probe_context.py` does **not** exist on master; `ProbeContext` has no `sibling_slices` field (per S4-01 hardened); existing test idiom (e.g., `tests/unit/probes/test_language_detection_extended.py:29-42`) constructs `RepoSnapshot` + `ProbeContext` inline | **PHANTOM** — helper + field both absent |
| Fixture file `.codegenie/context/raw/semantic_index.json` (AC-3, line 121, line 256) | S4-01 hardened AC-12 + cross-story integration handoff: B2 reads `<index_name>.json` keyed by `IndexName` stem; for `IndexName("scip")` the file is **`scip.json`** | **PHANTOM** — wrong filename; B2's `read_raw_slices` would treat `semantic_index.json` as an unrelated index and emit `Stale(IndexerError("upstream_scip_unavailable"))` because no `scip.json` exists |
| AC-3 option (b): "Pytest fixture that constructs the synthetic sibling slice in-memory" → passed as `ctx.sibling_slices["scip"]` | S4-01 (hardened): `sibling_slices` is **not** a `ProbeContext` field; B2 reads from disk via `read_raw_slices(raw_dir(repo.root))` — there is no in-memory injection seam | **PHANTOM** — the proposed Option (b) doesn't compile against master; only the on-disk path is real |
| AC-9: "clears the freshness registry via `_clear_for_tests()` (S1-02 helper)" | S1-02 ships `unregister_for_tests(index_name)` per `src/codegenie/indices/registry.py:165` — per-name, **not** a global clear | **PHANTOM** — same phantom as S4-01 caught; use the `clean_freshness_registry` snapshot-and-restore fixture from S4-01's TDD preamble |
| Vendored `.git/` at `tests/fixtures/portfolio/stale-scip/.git/` (AC-3 + implementer note line 276) | Git refuses to track a nested `.git/` directory as files; the repo-wide `.gitignore` line 1-3 ignores `.codegenie/` everywhere, so `.codegenie/context/raw/*.json` cannot be committed either | **MECHANICALLY IMPOSSIBLE** — the "vendored" plan does not work as written |
| AC-5 `regenerate.sh` guard: "invokes the script with a sentinel env that forces this branch" | The script (lines 102-133) assigns `LAST_INDEXED=$(git rev-parse HEAD)` locally **between** the two commits, then commits v1, then guards `if LAST_INDEXED == $(git rev-parse HEAD)`. Under normal flow LAST_INDEXED (= v0) ≠ HEAD (= v1); under no execution path does LAST_INDEXED equal HEAD. The guard is dead code as written and cannot be exercised via env | **DEAD CODE** — either the guard reads `LAST_INDEXED` from env (with fallback) so the test can force it, or the test patches a temp-copy of the script |

## Critic reports

### Coverage critic — HARDEN

Six findings (F1–F6):

- **F1 — Outer-key invariant not asserted at AC-1 step 1.** Story asserts `"scip" in
  slice["index_health"]`. After S4-01's hardened AC-10 (outer-key invariant —
  `set(slice["index_health"].keys()) == set(registered_names())`), a test that lets
  *other* registered checks slip in (e.g., a polluted singleton from a prior test)
  would still pass step 1. Strengthen: **`set(slice["index_health"].keys()) ==
  {"scip"}`** — the adversarial fixture exercises only the SCIP source; any
  additional key signals registry pollution (a real regression vector).
- **F2 — Discriminated-union round-trip uses `Stale.model_validate` not
  `TypeAdapter[IndexFreshness]`.** The story's `freshness = Stale.model_validate(raw)`
  silently bypasses the `Fresh | Stale` discriminator. A B2 regression that emits
  `Fresh(...)` would fail the validate call with an opaque kind-discriminator
  Pydantic message, not the more diagnostic "Expected `Stale`, got `Fresh(...)`".
  Use `TypeAdapter(IndexFreshness).validate_python(raw)` then
  `assert isinstance(freshness, Stale)` — this is the documented round-trip pattern
  for the sum type (S1-01 property tests) and is the right idiom for the adversarial.
- **F3 — `git` pre-flight check missing under AC-8's "no skip" discipline.** AC-8
  says "if git is missing, fail with clear message." But the actual mechanism wraps
  `git rev-parse HEAD` failure into `Stale(IndexerError("repo_not_a_git_workdir"))`,
  which produces "Expected `CommitsBehind`, got `IndexerError`" — correct but
  unhelpful. Add `shutil.which("git")` pre-flight at test start that
  `pytest.fail`s with an explicit hint.
- **F4 — "fixture not regenerated" vs. "fixture missing" not distinguished.** Test
  checks `FIXTURE.exists()` only. After hardening (the `.git/` is regenerated, not
  committed), the directory will exist on a clean checkout but `scip.json` and
  `.git/HEAD` will not. The fail message should point at `regenerate.sh`
  specifically when the seed files are missing inside the existing directory.
- **F5 — Time budget AC-10 not enforced in the test.** AC-10 says <10s but defers
  to the bench. A slow regression silently degrades CI. Pin in-test via
  `@pytest.mark.timeout(10)` (the pytest-timeout plugin is a Phase 0/1 dep
  precedent; confirm at implementation time).
- **F6 — No AC for `.gitignore` policy for the fixture tree.** The repo-wide
  `.gitignore` ignores `.codegenie/` everywhere. The seed material that lives
  inside `.codegenie/` must either (a) live at a tracked path (`_seed/scip.json`)
  and be copied by `regenerate.sh`, or (b) be re-allow-listed via a `!` exception
  line. Pick (a) — seed at `_seed/scip-slice.template.json`, `regenerate.sh` copies
  it with the parent SHA substituted in. This makes the seed material reviewable
  in the parent repo's git history.

### Test-quality critic — HARDEN

Mutation table for plausibly-wrong implementations the original TDD plan would let through:

| Plausibly-wrong implementation | Original TDD plan catches it? | After hardening |
|---|---|---|
| B2 silently returns `Fresh(indexed_at=now())` for the stale fixture (the load-bearing regression) | ✅ Yes — AC-1 step 2/3 would fail (with an unfriendly Pydantic kind-discriminator message) | ✅ With `TypeAdapter[IndexFreshness]`: "Expected `Stale`, got `Fresh(indexed_at=...)`" — the load-bearing failure mode is named directly |
| B2 emits `Stale(IndexerError("upstream_scip_unavailable"))` because `scip.json` is missing (silent fixture corruption) | ⚠ Partial — AC-1 step 3 fails with "expected `CommitsBehind`, got `IndexerError`" — correct outcome but the operator sees a confusing message and may waste time digging | ✅ AC-1 step 3 message names the fixture-corruption case explicitly: "`IndexerError` may indicate the fixture's `.codegenie/context/raw/scip.json` was not regenerated; run `regenerate.sh`" |
| Pollution: a prior test registers a `mock` freshness check in the singleton without unregistering; the adversarial's slice has both `mock` and `scip` keys | ❌ No — `"scip" in slice` succeeds; the extra `mock` key is invisible | ✅ AC-1 step 1 hardened to `set(slice.keys()) == {"scip"}` — pollution becomes a loud failure |
| `regenerate.sh` is silently modified to make HEAD == LAST_INDEXED (e.g., second commit removed) | ❌ No — guard is dead code; even modified-script invocations never trip it | ✅ Guard refactored to read `LAST_INDEXED` from env (`LAST_INDEXED="${LAST_INDEXED:-$(git rev-parse HEAD)}"`); `test_regenerate_sh_guard` invokes with `LAST_INDEXED=<HEAD>` and asserts exit 1 |
| `current_HEAD` derivation drifts from B2's exact path (e.g., test uses `text=True`, B2 uses `bytes` + decode) → false-pass when the underlying tool's encoding changes | ⚠ Tolerable — both produce the same string in practice | ✅ Pin the test's derivation to match B2's exact byte-decode shape; document the invariant |
| B2 emits the typed value but the slice contains both `freshness: <typed>` AND a stale `confidence: "high"` (per-source confidence wasn't re-derived) | ❌ No — story does not assert on the per-source `confidence` value | ✅ Add an additional assertion at AC-1 step 4: `slice["scip"]["confidence"] == "medium"` (per S4-01 AC-9's `CommitsBehind` → "medium" mapping) — verifies the demote-min wiring at the slice surface |

### Consistency critic — BLOCK (seven findings, all resolved)

- **B1:** `probe.run(ctx)` is one-arg. Master is two-arg. Fix to `probe.run(snapshot, ctx)`.
- **B2:** `build_probe_context` + `sibling_slices=` are phantom. Use inline
  `_snapshot`/`_ctx` idiom and on-disk `scip.json` for the sibling slice.
- **B3:** `semantic_index.json` is the wrong filename. B2 reads `scip.json` per
  S4-01 hardened cross-story handoff. Fix everywhere (Goal, AC-3, AC-4, Files-to-touch,
  Implementation outline).
- **B4:** AC-3 "Option (b) in-memory sibling_slices" is phantom; collapse to
  "fixture ships on-disk `scip.json`; no implementer-choice."
- **B5:** AC-9's `_clear_for_tests()` is phantom. Use `clean_freshness_registry`
  snapshot fixture per S4-01 TDD preamble.
- **B6:** Vendored `.git/` cannot work — repo-wide `.gitignore` ignores `.codegenie/`,
  and Git refuses nested `.git/` tracking. Restructure: commit `_seed/` material +
  `regenerate.sh` + `README.md`; `regenerate.sh` (or a conftest fixture) materializes
  `.git/` and `.codegenie/context/raw/scip.json` at first run.
- **B7:** `regenerate.sh` guard is dead code. Refactor with
  `LAST_INDEXED="${LAST_INDEXED:-$(git rev-parse HEAD)}"` env-overrideable form
  so AC-5's `test_regenerate_sh_guard` can exercise the guard branch deterministically.

### Design-pattern critic — four notes (DP1–DP4)

- **DP1 — Adversarial test fixture builder as a rule-of-three deferred kernel.**
  S4-02 is the FIRST of six (per [`phase-arch-design.md §"Adversarial tests"`](../../phase-arch-design.md))
  Phase-2 adversarial tests under `tests/adv/phase02/`: S5-05 (image-digest-drift),
  S5-06 (adversarial-dockerfile), S6-07 (secret-in-source), S7-04 (hostile-skills +
  concurrent-gather + no-inmemory-leak + phase3-handoff-skipped). Every one will
  construct `RepoSnapshot` + `ProbeContext` + invoke a single probe + assert structural
  outcome. The rule-of-three threshold is reached when the 3rd adversarial lands.
  Do NOT pre-extract in S4-02 (Rule 2 — simplicity first). Surface as a
  Notes-for-implementer pointer so the 3rd arrival recognizes the kernel-extract
  opportunity and lifts `tests/adv/phase02/_helpers.py` (mirroring the Phase-1
  precedent at `tests/adv/_helpers.py`).
- **DP2 — Fixture seed material at a tracked path, materialized at first run.**
  Splitting "what's reviewable in git" (`_seed/`, `regenerate.sh`, `README.md`) from
  "what's regenerated per-run" (`.git/`, `.codegenie/`) lets the parent repo's
  reviewer see exactly what the adversarial scenario *means* (the seed JSON, with
  a `PARENT_COMMIT` placeholder, names every assertion the test checks) without
  fighting `.gitignore` or `.git/` nesting. This is the same Functional-Core /
  Imperative-Shell discipline S4-01 enforces at the probe boundary, applied at the
  fixture boundary.
- **DP3 — `TypeAdapter[IndexFreshness]` as the round-trip-at-the-boundary idiom.**
  The discriminated union exists precisely so consumers can validate JSON →
  `IndexFreshness` without knowing which variant they'll get. The test using
  `Stale.model_validate` bypasses the discrimination; using `TypeAdapter` exercises
  the variant-selection logic that real consumers (S8-01's renderer, future Phase 3
  adapters) will use. Document this in Notes-for-implementer so future adversarials
  follow the same pattern.
- **DP4 — Open/Closed at the file boundary for adversarial tests.** Adding the
  next adversarial under `tests/adv/phase02/` must require zero edits to existing
  adversarial tests, zero edits to the `phase02_adv` marker registration (one marker
  per phase covers all), and zero edits to the `adv-phase02` CI YAML (S8-03 uses
  `pytest -m phase02_adv`). S4-02 already largely accomplishes this; the explicit
  statement in Notes-for-implementer makes the discipline visible to S5-05/S5-06/
  S6-07/S7-04.

## Stage 3 research

**Skipped.** No `NEEDS RESEARCH` findings. Every gap was answerable from:
- arch design (`phase-arch-design.md §"Process view" Scenario 2`, §"Edge cases" row 11,
  §"Adversarial tests");
- ADRs (02-ADR-0006 — variant set);
- High-level-impl.md §"Risks specific to this step" #3 — the both-inequalities rationale;
- S4-01's hardened story + validation report (the canonical Phase 2 precedent
  for "phantom Phase-0/1 surface vs. master" fixes);
- verified live source: `src/codegenie/probes/base.py:32-96`, `src/codegenie/indices/
  registry.py:139-175`, `src/codegenie/indices/freshness.py`, `src/codegenie/output/
  paths.py:20-21`, `tests/unit/probes/test_language_detection_extended.py:29-42`
  (existing test idiom), `tests/adv/_helpers.py` (Phase 1 adversarial helper precedent),
  repo-root `.gitignore`, `pyproject.toml:184-211`.

## Edits applied

| AC / section | Original | After hardening |
|---|---|---|
| Story header — Validation notes block | absent | New block summarizing seven BLOCK fixes + eight harden + four design notes |
| Status line | `Ready` | `Ready · VALIDATED (HARDENED — see _validation/S4-02-stale-scip-adversarial.md)` |
| Goal | `directory, .codegenie/context/raw/scip-index.scip placeholder, a hand-written index_health seed slice file (or equivalent harness input)` | Explicit on-disk path `scip.json` (B2 reads by stem per S4-01); seed material lives at tracked `_seed/scip-slice.template.json`; `regenerate.sh` materializes `.git/` + `.codegenie/context/raw/scip.json` at first run; the test path bypasses S4-03 (the SCIP probe doesn't run) |
| AC-1 step 1 | `"scip" in slice["index_health"]` | `set(slice["index_health"].keys()) == {"scip"}` — outer-key invariant (catches singleton pollution) |
| AC-1 step 2 | `freshness = Stale.model_validate(slice["index_health"]["scip"]["freshness"])` | `freshness = TypeAdapter(IndexFreshness).validate_python(slice["index_health"]["scip"]["freshness"])` then `assert isinstance(freshness, Stale)` — exercises the discriminated-union validation path, gives diagnostic "Expected `Stale`, got `Fresh(...)`" on the load-bearing regression |
| AC-1 step 5 (new) | absent | `slice["index_health"]["scip"]["confidence"] == "medium"` — pins S4-01 AC-9's `CommitsBehind` → "medium" demote-min wiring at the slice surface |
| AC-3 | "minimal `package.json`"; `.git/` vendored; `.codegenie/context/raw/scip-index.scip` placeholder; `semantic_index.json` harness input; Option (a)/(b) implementer choice | Restructured: **tracked** files are `regenerate.sh`, `README.md`, `_seed/scip-slice.template.json`, `_seed/scip-index.scip.placeholder` (optional empty bytes), `package.json`, `main.ts`. **Runtime** files (regenerated, gitignored) are `.git/`, `.codegenie/context/raw/scip.json` (substituted from the template), `.codegenie/context/raw/scip-index.scip`. Option (b) "in-memory sibling_slices" removed (phantom — `ProbeContext` has no `sibling_slices` field per S4-01 hardened). The on-disk `scip.json` is the only path B2 reads. |
| AC-4 | README mentions `semantic_index.json` | README updated: file is `.codegenie/context/raw/scip.json` (keyed by `IndexName` stem per S4-01); regenerate.sh produces it from `_seed/scip-slice.template.json` substituting `PARENT_COMMIT`; load-bearing structural assertion unchanged |
| AC-5 (regenerate.sh guard) | Guard is dead code (`LAST_INDEXED` always ≠ HEAD by script structure) | Guard refactored: `LAST_INDEXED="${LAST_INDEXED:-$(git rev-parse HEAD~1)}"` (env-overrideable with structural default of parent); `test_regenerate_sh_guard` invokes the script with `LAST_INDEXED="$(git -C tmp rev-parse HEAD)"` to force the guard branch deterministically |
| AC-7 (marker registration) | "implementer choice — pyproject.toml OR conftest.py" | Pinned to `pyproject.toml` (matches existing Phase 0/1 markers); `conftest.py` registers only the `fixture_path` fixture, not the marker |
| AC-8 (no skip path) | "fails with a clear 'git not on PATH' message" — but mechanism produces opaque `IndexerError` | Add `shutil.which("git") is not None` pre-flight at test start; on `None`, `pytest.fail(... explicit "git missing" message)`. Other failure modes still flow through B2's typed IndexerError. |
| AC-9 (no false-pass under empty registry) | "clears the freshness registry via `_clear_for_tests()` (S1-02 helper)" | Use the `clean_freshness_registry` snapshot-and-restore fixture from S4-01 TDD preamble (singleton-snapshot pattern); `_clear_for_tests` is phantom |
| AC-10 (time budget) | "10 s budget; bench catches creep" | Add `@pytest.mark.timeout(10)` on the adversarial test method (assuming `pytest-timeout` is available — verify at implementation; if not, scope a tiny `time.perf_counter()` start/end + assert at end of test) |
| AC-12 (new) | absent | `.gitignore` policy: the fixture tree is governed by repo-wide `.codegenie/` ignore + new fixture-local `.gitignore` for `.git/` — both runtime trees are gitignored; seed material at `_seed/` is tracked. Verified by `test_fixture_gitignore_policy` that asserts `git check-ignore` reports `.codegenie/` and `.git/` as ignored but `_seed/scip-slice.template.json` as tracked. |
| Implementation outline step 2 (regenerate.sh) | inlined script with dead guard + writes `semantic_index.json` + creates `.git/` "vendored" | Rewritten: script reads `_seed/scip-slice.template.json`, substitutes `PARENT_COMMIT` token with the v0 SHA, writes to `.codegenie/context/raw/scip.json`; env-overrideable guard; explicit `set -euo pipefail`; `SOURCE_DATE_EPOCH` pin so commit SHAs are reproducible (optional, mark as nice-to-have) |
| Implementation outline step 3 | "Decide harness input style; Option (b) preferred" | Removed — only on-disk path exists; the test passes nothing to B2 beyond `repo` + `ProbeContext` (both constructed inline matching existing test idiom) |
| Implementation outline step 4 | `out = asyncio.run(probe.run(ctx))` (one-arg) + `build_probe_context` + `Stale.model_validate` | `out = asyncio.run(probe.run(snapshot, ctx))` (two-arg); inline `_snapshot` and `_ctx` constructors mirroring `tests/unit/probes/test_language_detection_extended.py:29-42`; `TypeAdapter(IndexFreshness).validate_python(raw)` round-trip |
| Implementation outline step 6 | `test_regenerate_sh_guard` "invokes the script with a sentinel env that forces this branch" | Concrete: `LAST_INDEXED=$(git -C tmp rev-parse HEAD) bash regenerate.sh` in a `subprocess.run(..., env={"LAST_INDEXED": head, **os.environ})` call; asserts `returncode == 1` and stderr contains `"refuses to set last_indexed_commit == HEAD"` |
| Implementation outline step 7 | "clears the freshness registry via `_clear_for_tests()` (S1-02 helper)" | Use the `clean_freshness_registry` snapshot fixture; the test registers nothing inside the clean window, so `registered_names()` is empty; B2 emits `slice == {}`; the adversarial assertion fails at step 1 (proving AC-9) |
| Files-to-touch | `tests/fixtures/portfolio/stale-scip/.git/` (real git work tree — initialized by `regenerate.sh`) listed under "Run once (artifacts committed)" | `.git/` and `.codegenie/` moved to "Runtime, NOT committed" (gitignored per fixture-local `.gitignore`); `_seed/scip-slice.template.json` and `_seed/scip-index.scip.placeholder` added under "Create (committed)" |
| Notes for the implementer | duplicated from arch | + DP1 (rule-of-three deferred kernel for adversarial helpers) + DP2 (seed-at-tracked-path / runtime-materialized split) + DP3 (`TypeAdapter[IndexFreshness]` round-trip discipline) + DP4 (Open/Closed at file boundary for new adversarials) + explicit cross-story handoff note (S4-02 ships the substitute for S4-03's not-yet-existent `scip.json` writer; the fixture's seed slice is the contract surface S4-03 must honor when it ships) |

## Verdict rationale

**HARDENED.** The story's intent — encoding the Phase 2 roadmap exit criterion as a
CI-gating typed adversarial — is correct against [`phase-arch-design.md §"Goals" G2`](../../phase-arch-design.md),
[02-ADR-0006](../../ADRs/0006-index-freshness-sum-type-location.md), and the
`High-level-impl.md §"Risks specific to this step" #3` rationale for the both-inequalities
structural assertion. After hardening:

- All seven BLOCK findings closed by realigning prescriptions to actual master
  surfaces (`Probe.run(repo, ctx)`, inline test-context construction, `scip.json`
  filename per S4-01 hardened, `clean_freshness_registry` snapshot fixture,
  `_seed/` + `regenerate.sh` materialization split, env-overrideable guard).
- All eight HARDEN findings closed: outer-key invariant (F1), `TypeAdapter`
  round-trip (F2), git pre-flight (F3), fixture-corruption-vs-missing fail message
  (F4), timeout enforcement (F5), `.gitignore` policy (F6), per-source confidence
  pin (mutation table row 6), and B2-path-mirror byte-decode (mutation table row 5).
- Four design-pattern notes added: rule-of-three deferred kernel for the next
  five adversarials (DP1), seed-at-tracked-path / runtime-materialized split (DP2),
  `TypeAdapter[IndexFreshness]` round-trip discipline (DP3), Open/Closed at the
  file boundary for new adversarials (DP4).

The story is now executor-ready. The structural assertion that makes Phase 2's exit
criterion real (`Stale(reason=CommitsBehind(n>=1, last_indexed != HEAD))`) is
preserved verbatim; only the *prescriptions for getting there* have been corrected
to match the master surface S4-01 (hardened) established.
