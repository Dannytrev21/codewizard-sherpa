# Story S2-05 — Cache-hit-on-real-repo integration test (two probes)

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Ready (Hardened 2026-05-14)
**Effort:** M
**Depends on:** S2-03 (canonical fixture `node_typescript_helm/`), S2-04 (sibling integration test that lands `tests/integration/probes/conftest.py` with the autouse seam-disablement + shared helpers)
**ADRs honored:** ADR-0002 (memo is per-gather and does not interfere with cross-gather cache behavior; cache key derives from `content_hash`, not live `os.stat`), ADR-0004 (envelope still validates after a cache-hit gather), ADR-0010 (slice optionality — non-Node repos out of scope here)

## Validation notes (2026-05-14)

Hardened by `phase-story-validator`. Full audit at [`_validation/S2-05-cache-hit-integration-two-probe.md`](_validation/S2-05-cache-hit-integration-two-probe.md). Summary of changes:

- **BLOCK — replaced nonexistent harness symbols.** The original draft prescribed `from codegenie.cli import gather_in_process`, a `structlog_capture` pytest fixture, and `from codegenie.schema import load_envelope_validator` — **none of these exist** in the codebase. The actual Phase 0 / S2-04 precedent is `click.testing.CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])` paired with `structlog.testing.capture_logs()` as a *context manager* and `from codegenie.schema.validator import validate`. All three references rewritten.
- **BLOCK — replaced the global-`os`-mutating monkeypatch with the module-local shim.** The original Implementation outline #7 used `monkeypatch.setattr(ld_mod.os, "scandir", counting)`. Since `ld_mod.os IS os`, that form mutates the **global** `os` module — every `os.scandir` call anywhere in the process (cache layer, output writer, audit chain, pytest internals) increments the counter and produces false-RED on the warm run. Phase 0's S4-04 was hardened on this exact bug ([`tests/smoke/conftest.py`](../../../../tests/smoke/conftest.py) — `_install_scandir_counter`); the helper replaces the `os` *name binding* on the probe module with a `types.SimpleNamespace` shim mirroring every public attribute of `os` plus a counting `scandir`. The story now mandates `_install_scandir_counter(monkeypatch, ld_mod)`.
- **BLOCK — surfaced the load-bearing autouse `_disable_cli_configure_logging`.** S2-04's hardened story already requires this in `tests/integration/probes/conftest.py`; S2-05 depends on the same fixture. Without it, `CliRunner.invoke` re-runs `codegenie.cli._seam_configure_logging`, replaces structlog's processor chain, clobbers the `capture_logs()` chain, and every `probe.cache_hit` count silently collapses to 0 — a misleading RED that consumes executor retries.
- **HARDEN — added negative-variant ACs.** S4-04's hardening established that `probe.cache_hit` alone is not enough — the test must also assert `probe.success` does **not** fire on the warm run for either probe (a buggy impl could emit both events and pass). The new ACs also assert `cache_key` byte-equality across cold and warm runs for both probes (proves the cache-key invariance, not just that *some* hit blob was found).
- **HARDEN — added a metamorphic miss-partner test.** Without one, an `always-return-CacheHit` mutant passes every other AC in this story. The new `test_two_probes_cache_miss_on_tracked_input_edit` test edits a tracked input (`package.json` is in both probes' `declared_inputs`) and asserts the cache misses for both probes — symmetric counterpart to the hit test. Same metamorphic pattern Phase 0's S4-04 carries.
- **HARDEN — fail-loud slice assertions.** A buggy probe could ship `probe.cache_hit` and a corrupt slice (warnings, degraded confidence) and pass the original story. Mirroring S2-04, the post-cache-hit envelope now asserts `errors == []`, `warnings == []`, `node_build_system.confidence == "high"`, and `framework_hints == ["express"]` for both probes — the cache MUST replay the same byte-equivalent slice on the warm run.
- **HARDEN — normalized `_stat_snapshot` to POSIX-form path strings.** ADR-0002 documents the macOS case-insensitive Path-equality foot-gun. The snapshot helper now returns `dict[str, tuple[int, int]]` (keyed by `str(p.resolve())`), not `dict[Path, ...]`.
- **DESIGN-PATTERN AC (Open/Closed) — rule-of-three kernel.** S2-04 lands `_copy_tree` + `_load_envelope` + `_minimal_valid_envelope` + `_count_memo_events` in `tests/integration/probes/conftest.py`. S2-05 adds `_install_scandir_counter` + `_stat_snapshot` + a `WARM_PATH_CACHE_HIT_PROBES: frozenset[str]` constant. S5-05 extends to all six probes by **adding one item** to the frozenset (one-line edit) — never by editing the test body. Expressed as an observable AC: "adding the next probe to the warm-path assertion must require a single-line edit to `WARM_PATH_CACHE_HIT_PROBES` and zero edits to `_install_scandir_counter`, `_stat_snapshot`, or any test function body." The `_install_scandir_counter` helper is **re-exported** in `tests/integration/probes/conftest.py` from the existing `tests/smoke/conftest.py` source — one source of truth, no copy-paste.

## Context

This story lands the **load-bearing Phase 1 exit criterion #2** in its two-probe form: cache hits on the second run for `LanguageDetectionProbe` and `NodeBuildSystemProbe`. The same test file is extended in S5-05 to cover all six probes; this is the seam test, mirroring Phase 0's bullet-tracer cache-hit-on-second-run anchor (`docs/phases/00-bullet-tracer-foundations/stories/S4-04-fixtures-smoke-cache-hit.md`).

The load-bearing technique is identical to Phase 0's: **monkeypatch `os.scandir` at the probe-module level**, run a cold gather (warm the cache), run a second gather, and assert the monkeypatched callable's invocation count is **zero** on the second run. If the cache is honoured, no probe-internal walk occurs; if the cache is broken (wrong key derivation, mtime drift, sub-schema mismatch invalidating the slice), the walk fires and the count is non-zero.

Phase 0's lesson — restated here verbatim from the bullet-tracer notes — is that the monkeypatch target name must match how the probe imports `scandir`. The Phase 0 probe documents which name to patch in its module docstring; S2-01's refactor step adds the same docstring note. This story relies on that note being correct.

The redundant `probe.cache_hit` structlog assertion is the secondary signal: even if the monkeypatch target drifts and the invocation-count assertion silently passes, the structlog event count would catch the regression. **Both** assertions are required.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Scenarios" (Phase 0 sense)` — Phase 0's `phase-arch-design.md §"Scenarios — Scenario 2: Warm gather (cache hit, the bullet tracer's load-bearing exit)"` is the structural precedent. This phase's `../phase-arch-design.md §"Control flow"` happy-path describes the same flow with five additional probes.
  - `../phase-arch-design.md §"Gap analysis & improvements" → "Gap 1"` — pre-dispatch input-snapshot pass (S1-08) is what makes the cache key TOCTOU-safe across this two-gather sequence.
  - `../phase-arch-design.md §"Edge cases"` row 16 (mid-gather mtime change) — orthogonal to this test, but adjacent: this test deliberately does **not** edit files between gathers, so the cache key is identical.
  - `../phase-arch-design.md §"Testing strategy" → "Test pyramid"` — this is in the integration tier.
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — the memo is per-gather; this test runs two gathers, so the memo is constructed twice; the **cache** is across-gather and is what carries the load. The ADR also documents the cache key derives from `content_hash` (not live `os.stat`), so the `_stat_snapshot` pre/post check is belt-and-suspenders — not the cache-key invariance proof. ADR also documents the macOS case-insensitive-FS `Path` equality foot-gun (resolve to POSIX-form strings).
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — the warm-cache replay must still produce an envelope that validates under each per-probe sub-schema's strict root.
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — the canonical fixture is a Node repo, so both Layer A slices ARE present; the optionality of slices is exercised by Phase 1's non-Node fixture (out of scope here).
- **Source design:**
  - `../../../localv2.md §11` (caching layer).
- **Precedent (Phase 0, hardened):**
  - [`tests/smoke/test_cli_end_to_end.py`](../../../../tests/smoke/test_cli_end_to_end.py) — `test_cache_hit_on_second_run` + `test_cache_miss_on_tracked_input_edit` is the canonical metamorphic pair this story extends to two probes. Read both before writing. The `_invoke_gather(fixture)` helper at line 87 is `CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])` — global flags BEFORE the subcommand (click left-to-right option binding).
  - [`tests/smoke/conftest.py`](../../../../tests/smoke/conftest.py) — the source of truth for `_install_scandir_counter(monkeypatch, ld_mod) -> dict[str, int]` (the `SimpleNamespace`-shim pattern; module docstring lines 9–27 document **why** the naive `monkeypatch.setattr(ld_mod.os, "scandir", ...)` form produces false-RED) and the autouse `_disable_cli_configure_logging` fixture. S2-05's integration conftest **re-exports** the counter helper — does not copy it.
- **Sibling (Phase 1, S2-04 hardened):**
  - [`tests/integration/probes/conftest.py`](../../../../tests/integration/probes/conftest.py) (lands in S2-04) — carries the autouse `_disable_cli_configure_logging`, plus `_copy_tree`, `_load_envelope`, `_minimal_valid_envelope`, `_count_memo_events`. S2-05 extends this conftest with `_stat_snapshot` and re-exports `_install_scandir_counter` from `tests/smoke/conftest.py` (or, equivalently, lifts both to a project-root `tests/conftest.py` — implementer's call).
- **Existing code:**
  - `tests/fixtures/node_typescript_helm/` (from S2-03).
  - [`src/codegenie/probes/language_detection.py`](../../../../src/codegenie/probes/language_detection.py) — uses `import os` (module-local binding); the patch target is the `os` name binding via `monkeypatch.setattr(ld_mod, "os", shim)` — **never** `monkeypatch.setattr(ld_mod.os, "scandir", ...)` which mutates the shared `os` module.
  - [`src/codegenie/probes/node_build_system.py`](../../../../src/codegenie/probes/node_build_system.py) — does **not** call `os.scandir` (lockfile-precedence + tsconfig walks use `Path.exists()` + `jsonc.load`). The scandir-counter therefore only watches `language_detection`'s walks; the `probe.cache_hit` structlog event is the load-bearing signal for `node_build_system`.
  - [`src/codegenie/coordinator/coordinator.py:313`](../../../../src/codegenie/coordinator/coordinator.py) — `_log.info("probe.cache_hit", probe=name, cache_key=key, run_id=run_id)` is the event format the test asserts. The `cache_key` field is what enables byte-equality across the two runs.
  - [`src/codegenie/logging.py:32`](../../../../src/codegenie/logging.py) — `EVENT_PROBE_CACHE_HIT = "probe.cache_hit"` event constant.
  - [`src/codegenie/schema/validator.py`](../../../../src/codegenie/schema/validator.py) — public API is `from codegenie.schema.validator import validate`; raises `SchemaValidationError`. **No** `load_envelope_validator` symbol exists.
  - `src/codegenie/cache/...` — the on-disk content-addressed cache layer.

## Goal

Running `codegenie gather <fixture>` twice in succession against a `tmp_path` copy of `node_typescript_helm/`, with the `language_detection` module's `os` name binding replaced by a `SimpleNamespace`-shim that counts `scandir` invocations, results in **zero** counted invocations on the second run AND **exactly one** `probe.cache_hit` structlog event for each of `language_detection` and `node_build_system` AND **zero** `probe.success` events (with `cache_key`) for either probe on the second run AND a warm-run envelope whose `cache_key` is byte-equal to the cold run's and whose slice content (`framework_hints`, `package_manager`, `errors`, `warnings`, `confidence`) is byte-equal to the cold-run envelope.

## Acceptance criteria

### Test-file existence + harness wiring

- [ ] **AC-1.** `tests/integration/probes/test_cache_hit_on_real_repo.py` exists and contains at least two test functions: `test_two_probes_cache_hit_on_second_run` and the metamorphic partner `test_two_probes_cache_miss_on_tracked_input_edit`.
- [ ] **AC-2.** `tests/integration/probes/conftest.py` (from S2-04) is extended to (a) re-export `_install_scandir_counter` from `tests.smoke.conftest` (one source of truth — no copy-paste) and (b) add `_stat_snapshot(root: Path) -> dict[str, tuple[int, int]]` returning `{str(p.resolve()): (p.stat().st_mtime_ns, p.stat().st_size) for p in <walk>}`. The autouse `_disable_cli_configure_logging` fixture already lands in S2-04; this story does not duplicate it. **Alternative satisfying AC-2:** lift `_install_scandir_counter` and `_disable_cli_configure_logging` to a project-root `tests/conftest.py` so both `tests/smoke/` and `tests/integration/probes/` inherit them — at that point the smoke-conftest re-export can be deleted. Either path satisfies the AC; the implementer judges based on PR blast radius.
- [ ] **AC-3.** The test invokes the CLI via `click.testing.CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])` — global flags **before** the subcommand (click's left-to-right option binding; mirrors [`tests/smoke/test_cli_end_to_end.py:87`](../../../../tests/smoke/test_cli_end_to_end.py) `_invoke_gather`). **Not** `subprocess.run` (capture chain lives in this process). **Not** an invented `gather_in_process` helper — it does not exist.
- [ ] **AC-4.** The test uses `from structlog.testing import capture_logs` as a **context manager** wrapping the `CliRunner.invoke` call (one `with` block per gather; clear-between-gathers semantics via separate `with` blocks). No `structlog_capture` / `caplog_structlog` fixture is used or expected — none exists.
- [ ] **AC-5.** Module-local scandir shim is installed via `_install_scandir_counter(monkeypatch, ld_mod)` (where `ld_mod` is `codegenie.probes.language_detection`), **never** via `monkeypatch.setattr(ld_mod.os, "scandir", ...)` (which mutates the global `os` module — see Phase 0 S4-04 §"Notes for the implementer / TQ-1" for the false-RED failure mode this closes). The counter must be installed **after** the cold run completes and **before** the warm run begins.

### Stat-snapshot fixture-immutability invariant (belt-and-suspenders, ADR-0002)

- [ ] **AC-6.** Pre-cold-gather stat-snapshot is captured via `_stat_snapshot(repo)`. Post-cold-gather, the snapshot is recomputed; assert byte-equal to the pre-snapshot via `assert post == pre, {<key>: (pre[k], post[k]) for k in set(pre) ^ set(post) | {k for k in pre if pre[k] != post.get(k)}}` (or equivalent failure-message that names the offending keys; do not just `assert post == pre`). The snapshot dict is keyed by `str(p.resolve())` — POSIX-form path strings — to dodge the macOS case-insensitive-FS Path-equality foot-gun documented in ADR-0002.

### Load-bearing two-probe cache-hit assertion (Scenario 2 from `phase-arch-design.md §Scenarios`)

- [ ] **AC-7.** Cold run exit code is 0 with `result.output` included in the failure message. `<fixture>/.codegenie/context/repo-context.yaml` exists post-cold.
- [ ] **AC-8.** Both probes emit exactly one `event == "probe.success"` (carrying `cache_key`) on the cold run — `cold_keys = {e["probe"]: e["cache_key"] for e in cold_logs if e["event"] == "probe.success" and "cache_key" in e and e["probe"] in WARM_PATH_CACHE_HIT_PROBES}`; assert `set(cold_keys) == WARM_PATH_CACHE_HIT_PROBES`. The frozenset constant `WARM_PATH_CACHE_HIT_PROBES = frozenset({"language_detection", "node_build_system"})` lives in `tests/integration/probes/conftest.py` so S5-05 extends to all six via a one-line edit.
- [ ] **AC-9.** Warm run exit code is 0 with `result.output` in the failure message.
- [ ] **AC-10.** Counted `scandir` invocations on the warm run is exactly **0** (`assert calls["count"] == 0, f"warm-run scandir count = {calls['count']}"`).
- [ ] **AC-11.** For **each probe** in `WARM_PATH_CACHE_HIT_PROBES`: exactly one `probe.cache_hit` event with `probe == <name>` fires on the warm run — `warm_hits = {e["probe"]: e for e in warm_logs if e["event"] == "probe.cache_hit" and e["probe"] in WARM_PATH_CACHE_HIT_PROBES}`; assert `set(warm_hits) == WARM_PATH_CACHE_HIT_PROBES`.
- [ ] **AC-12.** **Negative-variant pin (S4-04 TQ-3 precedent):** for **each probe** in `WARM_PATH_CACHE_HIT_PROBES`, **zero** `probe.success` events carrying `cache_key` fire on the warm run — pins the variant as `CacheHit` *instead of* `Ran`. `assert not any(e["event"] == "probe.success" and e["probe"] in WARM_PATH_CACHE_HIT_PROBES and "cache_key" in e for e in warm_logs), warm_logs`.
- [ ] **AC-13.** **Cache-key byte-equality (S4-04 TQ-3 precedent):** for each probe, `warm_hits[probe]["cache_key"] == cold_keys[probe]` — proves the cache-key invariance directly. A buggy impl that re-derived a different key but happened to find a different stored blob would fail this clause. *Gap-check:* if the coordinator's `probe.success` event for `node_build_system` does not yet carry `cache_key` at the time of execution, surface the gap in the executor's attempt log; the AC may be relaxed to *only* `language_detection` and the `node_build_system` invariance dropped, **but** AC-10 (zero scandir) and AC-11 (cache_hit event count) and AC-12 (no probe.success on warm) collectively still pin the invariant; the byte-equality is the redundant signal, not the sole signal.

### Slice-content invariance across cold and warm (fail-loud, Rule 12)

- [ ] **AC-14.** The warm-run envelope's `probes.language_detection.language_stack.framework_hints == ["express"]` (exact equality, not membership) AND `probes.language_detection.language_stack.monorepo is None` AND `probes.language_detection.errors == []` AND `probes.language_detection.warnings == []`. The cache MUST replay the same slice — a silent corruption is a fail-loud failure mode this AC catches.
- [ ] **AC-15.** The warm-run envelope's `probes.node_build_system.package_manager == "pnpm"` AND `probes.node_build_system.errors == []` AND `probes.node_build_system.warnings == []` AND `probes.node_build_system.confidence == "high"`. Same fail-loud rationale.
- [ ] **AC-16.** Envelope schema validation: the warm-run YAML parses under `from codegenie.schema.validator import validate; validate(envelope)` with no `SchemaValidationError`. Asserted via the `_load_envelope(repo)` helper from `tests/integration/probes/conftest.py` (S2-04 lands the helper).

### Cache-miss metamorphic partner (mutation-resistance for the cache invariant)

- [ ] **AC-17.** `test_two_probes_cache_miss_on_tracked_input_edit` (metamorphic partner of AC-7..AC-16):
  - Copy the fixture; cold gather; assert exit 0 and capture cold cache keys (per AC-8 shape).
  - Edit `<repo>/package.json` (append a no-op JSON property — `"_test_edit": true` inside an existing object key, or rewrite-as-is via `json.dumps(json.loads(...) | {"_test_edit": True})`). `package.json` IS in **both** probes' `declared_inputs`, so both caches must miss.
  - Install `_install_scandir_counter`.
  - Warm gather; assert exit 0.
  - For each probe in `WARM_PATH_CACHE_HIT_PROBES`: **no** `probe.cache_hit` event fires on the warm run.
  - For each probe in `WARM_PATH_CACHE_HIT_PROBES`: exactly one `probe.success` event carrying `cache_key` fires on the warm run.
  - For each probe in `WARM_PATH_CACHE_HIT_PROBES`: `warm_success_keys[probe] != cold_keys[probe]` (key re-derived from changed inputs).
  - The scandir counter recorded **> 0** invocations on the warm run (the probe re-walked because the cache missed).

### Design-pattern AC (Open/Closed, rule-of-three) — extension by addition

- [ ] **AC-18.** S5-05's extension to all six probes must require **exactly one** edit: adding probe names to `WARM_PATH_CACHE_HIT_PROBES` in `tests/integration/probes/conftest.py`. Zero edits to `_install_scandir_counter`, `_stat_snapshot`, or any test function body. Asserted at story-execution time by writing the test functions as iterations over the frozenset — never as named-probe-by-named-probe assertions. A grep at S5-05 time for `"language_detection"` / `"node_build_system"` in `tests/integration/probes/test_cache_hit_on_real_repo.py` should return zero hits **outside** the frozenset constant declaration and any human-readable docstring; the *test bodies* parametrize over the constant.

### Static + dynamic gates

- [ ] **AC-19.** `ruff check tests/integration/probes/test_cache_hit_on_real_repo.py tests/integration/probes/conftest.py` passes.
- [ ] **AC-20.** `ruff format --check tests/integration/probes/test_cache_hit_on_real_repo.py tests/integration/probes/conftest.py` passes.
- [ ] **AC-21.** `mypy --strict tests/integration/probes/test_cache_hit_on_real_repo.py tests/integration/probes/conftest.py` passes (no `Any` slip-throughs; `list[dict[str, Any]]` is the captured-event list shape; `_stat_snapshot` returns `dict[str, tuple[int, int]]`).
- [ ] **AC-22.** `pytest tests/integration/probes/test_cache_hit_on_real_repo.py` exits 0 (both test functions pass).
- [ ] **AC-23.** Second-run wall-clock is **not** asserted in this story (advisory benches land in S6-02). The scandir counter, the `probe.cache_hit` event count, the cache-key byte-equality, and the slice-content invariance are the four redundant signals — wall-clock is the fifth and lives in the bench tier.

## Implementation outline

1. **Extend `tests/integration/probes/conftest.py`** (lands in S2-04; this story adds two items):
   - `from tests.smoke.conftest import _install_scandir_counter` and `__all__` re-export — one source of truth, no copy-paste. (Or alternative: lift `_install_scandir_counter` + `_disable_cli_configure_logging` to a project-root `tests/conftest.py` and delete the smoke-side definitions.)
   - `WARM_PATH_CACHE_HIT_PROBES: Final[frozenset[str]] = frozenset({"language_detection", "node_build_system"})` — the Open/Closed constant S5-05 extends by one-line edit.
   - `_stat_snapshot(root: Path) -> dict[str, tuple[int, int]]` returning `{str(p.resolve()): (p.stat().st_mtime_ns, p.stat().st_size) for p in root.rglob("*") if p.is_file()}`. Keys are POSIX-form resolved strings (ADR-0002 macOS Path-equality foot-gun).
2. **Add `tests/integration/probes/test_cache_hit_on_real_repo.py`** with two test functions:
   - `test_two_probes_cache_hit_on_second_run(tmp_path, monkeypatch)`
   - `test_two_probes_cache_miss_on_tracked_input_edit(tmp_path, monkeypatch)`
3. **Invocation pattern** (mirror [`tests/smoke/test_cli_end_to_end.py:87`](../../../../tests/smoke/test_cli_end_to_end.py)):
   ```python
   from click.testing import CliRunner
   from structlog.testing import capture_logs
   from codegenie.cli import cli

   def _invoke_gather(repo: Path) -> object:
       return CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])

   with capture_logs() as cold_logs:
       result_cold = _invoke_gather(repo)
   # ... assertions on cold_logs ...
   with capture_logs() as warm_logs:
       result_warm = _invoke_gather(repo)
   # ... assertions on warm_logs ...
   ```
   The S2-04 autouse `_disable_cli_configure_logging` keeps the structlog chain alive across `CliRunner.invoke`. Without it, both `cold_logs` and `warm_logs` are silently empty and every event-count AC fails with a misleading RED.
4. **Cache-hit test body** (AC-7..AC-16):
   - `repo = _copy_tree(FIXTURE, tmp_path / "repo")` (helper lands in S2-04 conftest).
   - `pre = _stat_snapshot(repo)`.
   - Cold gather inside `with capture_logs() as cold_logs:`; assert exit 0.
   - `post = _stat_snapshot(repo)`; assert `post == pre` with named-key diff in the failure message (AC-6).
   - Capture `cold_keys = {e["probe"]: e["cache_key"] for e in cold_logs if e["event"] == "probe.success" and "cache_key" in e and e["probe"] in WARM_PATH_CACHE_HIT_PROBES}`; assert `set(cold_keys) == WARM_PATH_CACHE_HIT_PROBES, cold_logs` (AC-8). Includes `cold_logs` in failure message for diagnostics.
   - `import codegenie.probes.language_detection as ld_mod`.
   - `calls = _install_scandir_counter(monkeypatch, ld_mod)`.
   - Warm gather inside `with capture_logs() as warm_logs:`; assert exit 0.
   - `assert calls["count"] == 0, f"warm-run scandir count={calls['count']}, warm_logs={warm_logs}"` (AC-10).
   - Build `warm_hits = {e["probe"]: e for e in warm_logs if e["event"] == "probe.cache_hit" and e["probe"] in WARM_PATH_CACHE_HIT_PROBES}`; assert `set(warm_hits) == WARM_PATH_CACHE_HIT_PROBES, warm_logs` (AC-11).
   - Assert `not any(e["event"] == "probe.success" and e["probe"] in WARM_PATH_CACHE_HIT_PROBES and "cache_key" in e for e in warm_logs), warm_logs` (AC-12).
   - For each `probe in WARM_PATH_CACHE_HIT_PROBES`: `assert warm_hits[probe]["cache_key"] == cold_keys[probe], (probe, warm_hits[probe], cold_keys[probe])` (AC-13).
   - `envelope = _load_envelope(repo)`; assert slice content (AC-14, AC-15); `from codegenie.schema.validator import validate; validate(envelope)` (AC-16).
5. **Cache-miss test body** (AC-17): symmetric counterpart. Edit `<repo>/package.json` via `json.dumps(json.loads(p.read_text()) | {"_test_edit": True})` (a tracked input change for BOTH probes — `package.json` is in both probes' `declared_inputs`). The same scandir-counter is installed before the warm run. Assertions flip: no `probe.cache_hit`, one `probe.success` carrying `cache_key` per probe, `warm_success_keys[probe] != cold_keys[probe]`, `calls["count"] > 0`.
6. **Do NOT** add a `time.sleep()` between gathers — ADR-0002 confirms the cache key derives from `content_hash`, not live `os.stat`. The `_stat_snapshot` check is belt-and-suspenders, not the cache-key proof.
7. **Do NOT** capture structlog events across both gathers in a single `with`. Use **two separate `with capture_logs() as ...:` blocks** so the cold-run `probe.success` events do not contaminate the warm-run assertion stream.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/probes/test_cache_hit_on_real_repo.py`. Sibling: `tests/integration/probes/conftest.py` (extended in this story — autouse `_disable_cli_configure_logging` already lands in S2-04).

```python
# tests/integration/probes/test_cache_hit_on_real_repo.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from structlog.testing import capture_logs

from codegenie.cli import cli
from codegenie.schema.validator import validate

from tests.integration.probes.conftest import (
    WARM_PATH_CACHE_HIT_PROBES,
    _copy_tree,
    _install_scandir_counter,
    _load_envelope,
    _stat_snapshot,
)

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "node_typescript_helm"


def _invoke_gather(repo: Path) -> object:
    """``--no-gitignore`` is the documented Phase 0 override that avoids
    coupling integration tests to TTY-prompt behavior. Global flags
    BEFORE the subcommand (click left-to-right binding)."""
    return CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])


def _coordinator_success_keys(
    events: list[dict[str, Any]],
) -> dict[str, str]:
    """Build {probe: cache_key} from probe.success events that carry cache_key.
    Filtered to probes in WARM_PATH_CACHE_HIT_PROBES so a future Layer-A probe
    in S5-05 needs no changes to this helper."""
    return {
        e["probe"]: e["cache_key"]
        for e in events
        if e.get("event") == "probe.success"
        and "cache_key" in e
        and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    }


def test_two_probes_cache_hit_on_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 2 from phase-arch-design.md §Scenarios — the load-bearing
    Phase 1 exit criterion #2 in its two-probe form. Mutation-resistance is
    achieved across FOUR redundant signals: scandir count, cache_hit event
    count, no probe.success-with-cache_key on warm, cache_key byte-equality.
    """
    import codegenie.probes.language_detection as ld_mod

    repo = _copy_tree(FIXTURE, tmp_path / "repo")
    pre = _stat_snapshot(repo)

    # Cold gather — populates the cache; capture cold cache_keys.
    with capture_logs() as cold_logs:
        result_cold = _invoke_gather(repo)
    assert result_cold.exit_code == 0, result_cold.output

    # AC-6 — fixture immutability invariant (belt-and-suspenders).
    post = _stat_snapshot(repo)
    diff = {k: (pre.get(k), post.get(k)) for k in set(pre) ^ set(post)} | {
        k: (pre[k], post[k]) for k in pre.keys() & post.keys() if pre[k] != post[k]
    }
    assert post == pre, f"fixture drifted during cold gather; diff={diff}"

    # AC-8 — both probes emitted probe.success with cache_key on cold.
    cold_keys = _coordinator_success_keys(cold_logs)
    assert set(cold_keys) == WARM_PATH_CACHE_HIT_PROBES, (
        f"cold-run probe.success(cache_key) coverage; got={set(cold_keys)}, "
        f"events={cold_logs}"
    )

    # AC-5 — module-local scandir counter shim (NEVER monkeypatch.setattr(ld_mod.os, ...))
    calls = _install_scandir_counter(monkeypatch, ld_mod)

    # Warm gather — must hit the cache for BOTH probes.
    with capture_logs() as warm_logs:
        result_warm = _invoke_gather(repo)
    assert result_warm.exit_code == 0, result_warm.output

    # AC-10 — zero scandir invocations on warm path.
    assert calls["count"] == 0, (
        f"warm-run scandir count={calls['count']} (expected 0); warm_logs={warm_logs}"
    )

    # AC-11 — exactly one probe.cache_hit per probe on warm.
    warm_hits = {
        e["probe"]: e
        for e in warm_logs
        if e.get("event") == "probe.cache_hit"
        and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    }
    assert set(warm_hits) == WARM_PATH_CACHE_HIT_PROBES, (
        f"warm-run probe.cache_hit coverage; got={set(warm_hits)}, events={warm_logs}"
    )

    # AC-12 — NO probe.success(cache_key) on warm for either probe (variant pin).
    rogue_successes = [
        e
        for e in warm_logs
        if e.get("event") == "probe.success"
        and "cache_key" in e
        and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    ]
    assert not rogue_successes, (
        f"probe.success(cache_key) must NOT fire on cache-hit warm run; got={rogue_successes}"
    )

    # AC-13 — cache_key byte-equality across cold and warm for each probe.
    for probe in WARM_PATH_CACHE_HIT_PROBES:
        assert warm_hits[probe].get("cache_key") == cold_keys[probe], (
            f"{probe}: cache_key invariance broken; "
            f"cold={cold_keys[probe]!r} warm={warm_hits[probe].get('cache_key')!r}"
        )

    # AC-14 / AC-15 / AC-16 — slice content invariance + schema validity.
    envelope = _load_envelope(repo)
    lang = envelope["probes"]["language_detection"]
    nbs = envelope["probes"]["node_build_system"]

    assert lang["language_stack"]["framework_hints"] == ["express"], lang
    assert lang["language_stack"]["monorepo"] is None, lang
    assert lang["errors"] == [], lang
    assert lang["warnings"] == [], lang

    assert nbs["package_manager"] == "pnpm", nbs
    assert nbs["errors"] == [], nbs
    assert nbs["warnings"] == [], nbs
    assert nbs["confidence"] == "high", nbs

    validate(envelope)  # raises SchemaValidationError on bad shape


def test_two_probes_cache_miss_on_tracked_input_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metamorphic partner of test_two_probes_cache_hit_on_second_run.

    Edits ``package.json`` (a tracked input for BOTH probes' declared_inputs).
    Without this test, an ``always-return-CacheHit`` mutant passes every other
    AC in the story. Phase 0 S4-04 carries the same metamorphic pattern for
    one probe; this is the two-probe extension.
    """
    import codegenie.probes.language_detection as ld_mod

    repo = _copy_tree(FIXTURE, tmp_path / "repo")

    with capture_logs() as cold_logs:
        result_cold = _invoke_gather(repo)
    assert result_cold.exit_code == 0, result_cold.output

    cold_keys = _coordinator_success_keys(cold_logs)
    assert set(cold_keys) == WARM_PATH_CACHE_HIT_PROBES, cold_logs

    # Edit package.json — tracked input for BOTH probes.
    pkg = repo / "package.json"
    data = json.loads(pkg.read_text())
    data["_test_edit"] = True
    pkg.write_text(json.dumps(data, indent=2) + "\n")

    calls = _install_scandir_counter(monkeypatch, ld_mod)

    with capture_logs() as warm_logs:
        result_warm = _invoke_gather(repo)
    assert result_warm.exit_code == 0, result_warm.output

    # Probe re-walked because cache missed.
    assert calls["count"] > 0, (
        f"expected scandir > 0 on tracked-input change; got 0; warm_logs={warm_logs}"
    )

    # No cache_hit for either probe.
    warm_hits = [
        e
        for e in warm_logs
        if e.get("event") == "probe.cache_hit"
        and e.get("probe") in WARM_PATH_CACHE_HIT_PROBES
    ]
    assert not warm_hits, f"cache must NOT hit on tracked-input change; got={warm_hits}"

    # Exactly one probe.success(cache_key) per probe.
    warm_keys = _coordinator_success_keys(warm_logs)
    assert set(warm_keys) == WARM_PATH_CACHE_HIT_PROBES, (
        f"warm-run probe.success(cache_key) coverage on miss; got={set(warm_keys)}, "
        f"events={warm_logs}"
    )

    # Cache key changed for each probe (re-derived from new content_hash).
    for probe in WARM_PATH_CACHE_HIT_PROBES:
        assert warm_keys[probe] != cold_keys[probe], (
            f"{probe}: cache_key must change when tracked inputs change; "
            f"cold={cold_keys[probe]!r} warm={warm_keys[probe]!r}"
        )
```

Confirm both tests RED. The first will fail with one of:
- `ModuleNotFoundError` or `ImportError` on `_install_scandir_counter` / `_stat_snapshot` / `WARM_PATH_CACHE_HIT_PROBES` if the conftest extension has not landed (AC-2).
- `AssertionError` on the cold-run `probe.success(cache_key)` coverage if S3-05/coordinator does not emit `cache_key` on `probe.success` for `node_build_system` (gap-check; surface in attempt log).
- `AssertionError` on `calls["count"] == 0` if the cache layer is not wired (or the wrong patch-target — see AC-5 vs. the false-RED form).
- `AssertionError` on the `cache_hit` event coverage if `node_build_system` does not emit it (S2-02 wiring gap).
- `AssertionError` on the slice-content invariance if the cache replays a degraded slice.
- `SchemaValidationError` if the warm-run envelope diverges from the cached slice.

The second test (cache-miss) will RED similarly until the cache-key derivation correctly re-derives on tracked-input change. Commit, then GREEN.

### Green — make it pass

This test does not write production code — its purpose is to exercise the production paths already on disk (S1-07 memo, S2-01 framework hints, S2-02 build system, S3-01 cache, S3-05 coordinator). If a green assertion fails, the failure surfaces in production code, not here. Diagnostic-by-AC:

- **AC-10 fail (`calls["count"] > 0`)** → either the cache layer is not wired (coordinator dispatches the probe instead of returning the cached output), or the monkeypatch target is wrong (re-confirm `_install_scandir_counter` is being used; **not** `monkeypatch.setattr(ld_mod.os, "scandir", ...)` which mutates global `os` and counts EVERY scandir, not just the probe's).
- **AC-11 fail (cache_hit event missing for one probe)** → `coordinator.py:313` (`_log.info("probe.cache_hit", ...)`) is not firing for that probe; check that the coordinator's cache-lookup path is wired for `node_build_system`'s probe entry, not just `language_detection`.
- **AC-12 fail (rogue `probe.success` with `cache_key` on warm)** → the coordinator dispatched the probe AND returned a hit — race condition or double-emission bug.
- **AC-13 fail (cache_key byte-equality broken)** → key derivation is non-deterministic across runs. Likely culprit: `os.stat` rather than `content_hash` in the key (ADR-0002 Gap-1 closure broken). If the gap-check uncovers that `probe.success` for `node_build_system` doesn't carry `cache_key` yet, relax AC-13 to `language_detection` only and surface the gap in the executor's attempt log.
- **AC-14/15 fail (slice content drift between cold and warm)** → cache stores raw probe output, not the validated slice; `_ProbeOutputValidator` re-runs on warm and degrades the slice. Fix: cache must store the validated slice (Phase 0 ADR-0009 — `cache-hit-pass-through-coordinator-output`).
- **AC-16 fail (`SchemaValidationError`)** → cache writes back an envelope that diverges from the cached slice (serialization round-trip bug in `CacheStore`).
- **AC-17 cache-miss test fails (`calls["count"] == 0`)** → the cache is incorrectly returning a hit on a tracked-input change. Same coordinator bug as AC-10 but in the opposite direction; the metamorphic pair surfaces both.

The metamorphic pair (hit + miss) is the **single most important pair of tests in this story**. If either passes for the wrong reason, every Phase 1+ probe that relies on the cache invariant will silently degrade.

### Refactor — clean up

- Confirm `_install_scandir_counter` and `_stat_snapshot` live in `tests/integration/probes/conftest.py` (or are inherited from a project-root `tests/conftest.py` per AC-2's alternative path). The test file itself imports them — no inline duplicates.
- Confirm `WARM_PATH_CACHE_HIT_PROBES` is the single declaration site. Grep `"language_detection"` and `"node_build_system"` in the test file — they should appear ONLY in slice-content assertions (where the probe's identity is the assertion target — AC-14/15) and docstrings. The cache-hit and miss assertions parametrize over the frozenset.
- Add a module-level docstring at the top of the test file explaining: *why* `os.scandir` is the load-bearing target (because `LanguageDetectionProbe`'s walk is the dominant filesystem activity in Phase 1's warm-path; if the cache fails for it, the rest of the chain falls over); and *why* the metamorphic pair is non-negotiable (S4-04 §"Notes for the implementer" line at the top of `tests/smoke/test_cli_end_to_end.py` is the precedent).
- Confirm `mypy --strict` clean on both files.
- `ruff check` + `ruff format --check` clean.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/probes/test_cache_hit_on_real_repo.py` | New file — the metamorphic pair (hit + miss). Will be **extended** in S5-05 to cover all six probes by adding probe names to the `WARM_PATH_CACHE_HIT_PROBES` frozenset in `conftest.py` — **zero** edits to this file required. |
| `tests/integration/probes/conftest.py` | Already exists (lands in S2-04 with autouse `_disable_cli_configure_logging` + `_copy_tree` + `_load_envelope` + `_minimal_valid_envelope` + `_count_memo_events`). This story extends it with: (a) `from tests.smoke.conftest import _install_scandir_counter` (re-export, no copy-paste); (b) `_stat_snapshot(root: Path) -> dict[str, tuple[int, int]]`; (c) `WARM_PATH_CACHE_HIT_PROBES: Final[frozenset[str]] = frozenset({"language_detection", "node_build_system"})`. |
| `tests/conftest.py` (**optional alternative satisfying AC-2**) | If the implementer prefers the project-root lift, move `_install_scandir_counter` + `_disable_cli_configure_logging` here and delete the smoke-side definitions. Either path satisfies AC-2; choose based on PR blast radius. |

## Out of scope

- **Extension to all six probes** — S5-05 (the load-bearing Phase 1 exit criterion #2 in full form).
- **Wall-clock assertion** — S6-02 bench canary (`test_warm_path_latency.py`, advisory).
- **Cache-invalidation-scope test** (sub-schema bump invalidates only that probe's entries) — S3-06 extends `tests/unit/test_cache_invalidation_scope.py` for `node_manifest`'s catalog edits; the broader pattern is Phase 0's gap-#1 resolution.
- **TOCTOU-window test** (mid-gather edit) — S1-08 lands the unit test for the input-snapshot pass; this story is the integration confirmation that no mid-gather edit happens in the canonical fixture path.
- **Adversarial repo with hostile cache state** — Phase 2's adversarial corpus may extend; Phase 1 trusts the cache layer.

## Notes for the implementer

- **The monkeypatch target is the load-bearing detail (S4-04 TQ-1 precedent — no hedge).** [`src/codegenie/probes/language_detection.py`](../../../../src/codegenie/probes/language_detection.py) uses `import os` (top-level module-local binding). The `_install_scandir_counter` helper from [`tests/smoke/conftest.py`](../../../../tests/smoke/conftest.py) replaces the `os` *name binding* on the probe module with a `types.SimpleNamespace` shim — only the probe's `os.scandir` lookup hits the counter; global `os.scandir` is untouched. **Do NOT use** `monkeypatch.setattr(ld_mod.os, "scandir", ...)`: since `ld_mod.os IS os`, that form mutates the shared `os` module and every call site in the process (cache layer, audit chain, output writer, pytest internals) increments the counter — false-RED on the warm run. This bug was the entire reason S4-04 was hardened.
- **The autouse `_disable_cli_configure_logging` (from S2-04 conftest) is load-bearing — not optional.** `CliRunner.invoke` exits and re-enters Click's runtime, which calls `_seam_configure_logging` and replaces structlog's active processor chain. `capture_logs()` works by swapping its own `LogCapture` processor into that chain; a re-configure inside `invoke` blows it away and every captured-event list comes back empty. The S2-04 fixture no-ops the seam for the duration of the test. Verify on the cold run: at least two `probe.success` events (`language_detection` + `node_build_system`) must appear in `cold_logs` — if not, the capture is broken, not the implementation. *Same-conftest precondition:* this story extends the S2-04 conftest, not creates a parallel one — there must be ONE `tests/integration/probes/conftest.py`.
- **Use `CliRunner` + `capture_logs()`, never `subprocess.run`.** A subprocess gather emits to a different process's stderr and the `capture_logs()` chain (process-local) is empty. Phase 0 precedent is [`tests/smoke/test_cli_end_to_end.py:87`](../../../../tests/smoke/test_cli_end_to_end.py) `_invoke_gather`. Do **not** invent a `gather_in_process` helper; it doesn't exist.
- **Two separate `with capture_logs()` blocks (cold + warm).** Capturing across both gathers in a single `with` block pollutes the warm-run event stream with cold-run `probe.success` events and forces fragile by-ordinal filtering. The metamorphic pair uses two clean blocks.
- **The `_stat_snapshot` invariant is belt-and-suspenders, not the cache-key proof.** ADR-0002's Gap-1 resolution moves cache keys from live `os.stat` to `content_hash` derived from the input-snapshot pass. The mtime/size check catches a flaky filesystem (e.g., `.git` writing inside the fixture mid-gather) and refuses to continue — without it, the warm-run assertion is meaningless. The actual cache-key invariance proof is AC-13 (byte-equality of `cache_key` across cold and warm).
- **Don't add `time.sleep()` between gathers.** Cache keys derive from `content_hash`, not live `os.stat` — no mtime-granularity races to mask. Adding sleep masks real bugs (a content-hash mismatch on identical bytes) by waiting them out.
- **Two probes, four redundant signals.** The four signals proving the cache invariant are: (1) `calls["count"] == 0` (scandir), (2) one `probe.cache_hit` per probe (event coverage), (3) zero `probe.success(cache_key)` on warm for either probe (variant pin), (4) `warm_hits[probe]["cache_key"] == cold_keys[probe]` per probe (key byte-equality). The story requires all four. If any single signal could be dropped, a class of buggy implementations would silently pass. S4-04 §"Notes for the implementer" line "Don't drop any of the three when simplifying" applies here, with one extra signal.
- **`node_build_system` does not call `os.scandir`.** Lockfile-precedence + tsconfig walks use `Path.exists()` + `jsonc.load`. The scandir counter is therefore a proxy for `language_detection`'s walk only; the `probe.cache_hit` event count is the load-bearing signal for `node_build_system`. The redundancy is asymmetric but adequate.
- **Cache-key byte-equality (AC-13) may be a gap-check.** If S3-05's coordinator does not yet emit `cache_key` on `probe.success` for `node_build_system` (S2-02's probe registration), surface the gap in the executor's attempt log. The AC may be relaxed to `language_detection`-only, but the remaining three signals collectively still pin the invariant for both probes. **Do not weaken the AC by removing `node_build_system` from the frozenset — that would also relax AC-11 and AC-12.** Relax only the byte-equality clause.
- **S5-05 extends by addition.** This story's design-pattern AC (AC-18) makes the extension a one-line edit to `WARM_PATH_CACHE_HIT_PROBES`. Validate at write time: grep your own test file for `"language_detection"` and `"node_build_system"` literals — they should appear only in slice-content assertions (AC-14/15) and docstrings. The hit/miss assertions parametrize over the frozenset; never name probes individually in those loops.
- **`SchemaValidationError` carries the failing path inside the message string, not as a structured attribute today.** AC-16 just asserts `validate(envelope)` does not raise — no need to inspect message contents on the success path. If the warm-run envelope fails validation, the raised exception's message embeds `err.json_path` (JSONPath form), which is the diagnostic for the executor.
- **Sub-schema strictness (ADR-0004) is preserved on the cache-hit path.** AC-16 is the proof point: the cached slice is written through `OutputSanitizer` + `_ProbeOutputValidator` AND the envelope passes per-probe-sub-schema strict validation. If S3-03's writer caches raw probe output (not the validated slice), AC-16 will fail. The fix lives in `coordinator.py` / `cache/`, not here.
