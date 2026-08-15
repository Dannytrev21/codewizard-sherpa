# Validation report — S5-02 Plugin-directory probe-placement fence

**Date:** 2026-08-14
**Validator:** phase-story-validator (four-critic parallel pipeline + synthesizer)
**Verdict:** **HARDENED** — three consistency, two coverage, two test-quality (collapsing into one shared root cause), and two design-patterns findings at block-severity were reconciled and edited in place. Story is ready for `phase-story-executor`.
**Story:** [`../S5-02-probes-live-under-plugin-fence.md`](../S5-02-probes-live-under-plugin-fence.md)

---

## Stage 1 — Context brief

Read:
- Story (all sections).
- `docs/phases/07-migration-task-class/ADRs/0005-probes-live-under-plugin-not-core-tree.md` — primary source of truth. §Consequences names the fence file verbatim and lists the AST-assertions it must ship.
- `docs/phases/07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — confirms `tests/fence/` is out of scope for the byte-edit allowlist (new file is additive).
- `docs/phases/03-vuln-deterministic-recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the "audit + lint, not runtime" framing this fence inherits (Phase 3 ADR-0011).
- `docs/phases/07-migration-task-class/stories/S7-01-base-image-probe.md` §Goal / AC-1 — confirms `plugins/distroless-migration--node--npm/probes/base_image_probe.py`.
- `docs/phases/07-migration-task-class/stories/S7-02-shell-invocation-trace-probe.md` §Goal / AC-1 — confirms `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py`.
- `tests/fence/test_capability_fence.py` — the closest sibling (live scan + planted-positive with same `find_violations(roots=[...])` DI; frozen `Violation` dataclass; floor-guard-every-root; per-class parametrized planted-positive).
- `tests/fence/test_no_any_in_plugin_surface.py` — `walk_any_annotations` + `Violation` frozen dataclass + per-shape parametrize matrix.
- `tests/fence/test_plugin_protocol_frozen.py` — small, focused, structural.
- `src/codegenie/probes/registry.py` — the actual public API surface (`default_registry.all_probes()`), confirming the story's `_REGISTRY` reference is wrong.
- `src/codegenie/probes/base.py:78` — `applies_to_tasks: list[str]` with `["*"]` sentinel (confirms the raw list comparison is safe; no `TaskId` newtype exists).
- `pyproject.toml § requires-python = ">=3.11"` — confirms `Path.is_relative_to` is available.
- Prior `_validation/S5-01-phase7-byte-edit-allowlist-fence.md` — sibling report; validated the same-family patterns (refuse `Fence` ABC on Rule 2; frozen `Violation` dataclass; formalize `_attempts/` evidence).

## Stage 2 — Four parallel critics

Each critic returned a structured finding list. Summary below; full critic outputs archived in the session transcript.

### Coverage critic (10 findings — 2 block · 6 harden · 3 nit)

- **coverage-1 (block)** — Symlink / real-path bypass. AC-3's walker and AC-4's `startswith` do not resolve symlinks; a `src/codegenie/probes/base_image_probe.py -> ../../../plugins/.../probes/base_image_probe.py` symlink would satisfy import-from-core namespace, `inspect.getsourcefile` would return the plugin path (bypassing AC-4), and AC-3 depends on `rglob`'s inconsistent symlink handling.
- **coverage-2 (block)** — Import re-export / alias assignment reintroduces the forbidden name. AC-3 walks `ast.ClassDef` only; `from plugins... import BaseImageProbe` (`ast.ImportFrom`) or `BaseImageProbe = _RealClass` (`ast.Assign` / `ast.AnnAssign`) in `src/codegenie/probes/__init__.py` puts the forbidden name back in the core namespace — exactly the precedent ADR-0005 closes.
- **coverage-3 (harden)** — AC-4 default `applies_to_tasks=["*"]` sneak path. A plugin-authored probe that *forgets* to set the field defaults to `["*"]` and slips past the filter entirely.
- **coverage-4 (harden)** — Xfail-strict hand-off is fragile and undocumented at both endpoints. Manual "S7-01 implementer removes the marker" prose contract.
- **coverage-5 (harden)** — Missing AC-5 shapes: nested `ClassDef`, multiple classes per file, `.pyi` stubs, `NodeVisitor` generic_visit discipline.
- **coverage-6 (harden)** — Path portability. Story uses `Path(...)` mixed with `str.startswith(...)`; relative-to-cwd assumptions.
- **coverage-7 (harden)** — No meta-fence protecting the fence itself. Compare S5-01's `test_zero_allowlist_markers_at_step1_landing`.
- **coverage-8 (harden)** — `inspect.getsourcefile` returning `None` is under-specified; Notes say "skip with a loud reason" but a `types.new_class`-generated probe is exactly the malicious shape that should fail loudly.
- **coverage-9 (nit)** — AC-4 couples to private `_REGISTRY` (superseded by consistency-1 — public API found).
- **coverage-10 (nit)** — AC-4 does not positively scope by plugin directory shape (a probe at `/tmp/random.py` passes).
- **coverage-11 (nit)** — Honest-framing observability is docstring-only. Acceptable per sibling S5-01 pattern; no change.

### Test-Quality critic (10 findings — 3 block · 5 harden · 2 nit)

- **test-1 (block)** — AC-3 walker scope not planted-tested against the *real* core tree. Mutation to `_CORE_PROBE_ROOT` typo silently green-flags. Mirror `test_capability_fence.py::test_floor_guard_every_root_exists_and_non_empty` (lines 48–60).
- **test-2 (block)** — AC-3 walker not tested for recursion into subdirectories. `os.listdir`-mutation passes.
- **test-3 (block)** — AC-4's `startswith("src/codegenie/probes/")` is a silent no-op (absolute vs. relative path comparison). Guaranteed-pass even after a real Phase-7 violation ships. **Same root cause as coverage-1 and design-6.**
- **test-4 (harden)** — AC-4 strict-xfail hand-off fragility.
- **test-5 (harden)** — AC-1 docstring meta-check is trivially spoofable + no walker-liveness assertion.
- **test-6 (harden)** — AC-5 planted matrix missing high-value mutants (nested class, case drift, regex-vs-AST proof).
- **test-7 (harden)** — Missing monotonicity property test — the plant/unplant machinery is right there.
- **test-8 (harden)** — AC-6 is unenforceable prose ("Verified by running `pytest ...`; exit code 0").
- **test-9 (nit)** — AC-5.d 3-line evidence-block is unenforceable prose; mirror S5-01's formalized evidence-check test.
- **test-10 (nit)** — AC-2 xfail-strict hand-off has same fragility as test-4.

### Consistency critic (3 findings — 1 block · 1 harden · 1 nit; everything else CONSISTENT)

- **consistency-1 (block)** — Registry API mismatch. The story instructs importing `codegenie.probes.registry._REGISTRY`; that symbol does not exist. The module exposes `default_registry: Registry` with public `all_probes() -> tuple[type[Probe], ...]`. Existing convention: `tests/bench/test_cache_hit_dispatch.py:32` and `tests/fixtures/_shape_test_kernel.py:273-275` both use `from codegenie.probes.registry import default_registry` → `default_registry.all_probes()`. Story-as-written crashes on import.
- **consistency-2 (nit)** — Fence filename says "provenance primitive" but content is probe placement. Preserved verbatim from ADR-0005 §Consequences per Rule 11; add a Notes bullet warning implementers not to quietly rename.
- **consistency-3 (harden)** — AC-3 walker signature (`root: Path`) contradicts AC-5's requirement that the walker accept `_walker_roots: tuple[Path, ...]` for planted-fixture DI. Two signatures for the same function.
- **All other consistency checks passed:** file paths in `_EXPECTED_PHASE7_PROBE_LOCATIONS` match S7-01 / S7-02 verbatim; plugin `--` separator matches production ADR-0031 §Layout; `applies_to_tasks: list[str]` with `["*"]` sentinel is the ABC contract at `base.py:78`; ADR-0009 row 10 = `src/codegenie/plugins/loader.py`; S5-01 dep matches `stories/README.md` line 169; Phase 3 ADR-0011 exists as `0011-honest-framing-capability-sandboxedpath-pluginslock.md`; `pyproject.toml [tool.mypy]` keeps `strict = true` for `tests.*` (AC-9 is meaningful, not vacuous); fence file is a net-new file under `tests/fence/` (outside byte-edit-allowlist scope per ADR-0009).

### Design-Patterns critic (11 findings — 2 block · 4 harden · 5 nit)

- **design-2 (block)** — `Violation` dataclass, not `tuple[Path, int, str]`. Original shape is primitive-obsessed; **contradicts the sibling family** (`_capability_fence.Violation`, `_phase3_fence.Violation` are both frozen dataclasses). Rule 11 (match convention).
- **design-8 (block)** — AC-4 empty-registry: pick `pytest.mark.xfail(strict=True)`; drop the skip alternative. Skip-when-empty survives handoff drift silently — the whole point of the fence is fail-loud. Runtime `pytest.skip()` inside test body doesn't compose with strict-xfail; mixing is a footgun.
- **design-1 (harden)** — Rule-of-three: refuse extraction (mirror S5-01's `Fence` ABC refusal); add `# duplicate-of: src/codegenie/_capability_fence.py::find_violations` comment.
- **design-3 (harden)** — `_EXPECTED_PHASE7_PROBE_LOCATIONS` illegally-representable — wrap in `ExpectedProbe` frozen dataclass.
- **design-4 (harden)** — `_FORBIDDEN_PHASE7_PROBE_NAMES` duplicates data; derive from `_EXPECTED_PHASE7_PROBE_LOCATIONS` at module load.
- **design-6 (harden)** — Use `Path.resolve().is_relative_to(...)` over `str.startswith(...)`. **Same root cause as coverage-1 and test-3.** Python 3.11+ makes `is_relative_to` available.
- **design-5 (nit)** — `TaskId` newtype doesn't exist yet; Rule 2 says defer.
- **design-7 (nit)** — Public `iter_probes()` API as follow-up (recorded as Notes bullet).
- **design-9 (nit)** — Mechanical `# xfail-until:` marker — Rule 2 over-engineering; rejected.
- **design-10 (nit)** — Phase-8+ plugin roots already Out-of-scope in the story.
- **design-11 (nit)** — Single-purpose fence discipline already documented in Notes; record as strong dimension.

## Stage 3 — Researcher

**Not fired.** No critic finding tagged `NEEDS RESEARCH`. Every finding had a concrete, precedent-grounded proposed fix drawn from the sibling fence family (`_capability_fence`, `_phase3_fence`) or from the S5-01 validation report.

## Stage 4 — Synthesizer + Editor

**Priority:** Consistency > Coverage > Test-Quality > Design-Patterns.

**Cross-critic convergences (unanimous fixes):**
- **`Path.resolve().is_relative_to(...)` replaces `str.startswith(...)`** — coverage-1 + test-3 + design-6 all identify the same root cause. Applied globally.
- **`Violation` frozen dataclass replaces raw tuples** — design-2 + implicit primitive-obsession in every walker-touching finding. Applied.
- **`default_registry.all_probes()` replaces `_REGISTRY`** — consistency-1 is authoritative. Coverage-9 (nit) becomes moot.
- **Xfail hand-off** — design-8 (strict-xfail wins) + test-4 / coverage-4 (predicate must be runtime-computed) + test-10 reconciled by using `@pytest.mark.xfail(condition=<predicate>(), strict=True)`. Predicate reads `default_registry.all_probes()` at collection time. Skip alternative dropped.

**Conflict resolution:**
- **Coverage-8 vs. story's Notes** — Coverage says fail-loud on `inspect.getsourcefile is None`; original Notes said "skip with a loud reason." Coverage wins (Rule 12 — fail loud is the whole point of a fence). Notes rewritten.
- **Design-1 vs. rule-of-three temptation** — refused extraction, following S5-01's precedent. `# duplicate-of:` comment records the discipline.
- **Consistency-3 vs. AC-5 DI shape** — walker signature normalized to `roots: Iterable[Path]` (matches `_capability_fence.find_violations(roots=[...])`).

**Edits applied** (see story's `## Validation notes` block for the concise summary):
- **Status:** `Ready` → `HARDENED (phase-story-validator, 2026-08-14)`.
- **Validation notes block** appended after Status (13 numbered load-bearing edits + deferrals).
- **ADRs honored line** — added Phase 3 ADR-0011 (`0011-honest-framing-capability-sandboxedpath-pluginslock.md`).
- **References — where to look** — added exact-anchor references to `src/codegenie/probes/registry.py`'s `default_registry.all_probes()` API + `src/codegenie/probes/base.py:78`; added `tests/fence/test_capability_fence.py` as the primary sibling to mirror; added sibling-story pointers (S7-01 §AC-1, S7-02 §AC-1).
- **Context §3** — rewritten to describe the AST-plus-name-binding scope (not just `ClassDef`) and the bidirectional invariant.
- **Goal §** — extended to name the three shapes rejected (class, import re-export, alias assignment).
- **AC-1** — added AC-1.b (walker-liveness meta-check) and AC-1.c (floor guard, mirroring `test_capability_fence.py`).
- **AC-2** — xfail marker made data-driven: `condition=_no_phase7_probes_registered()` (strict); dropped the "at story-landing time" ambiguity.
- **AC-3** — extended to walk `ast.ClassDef` + `ast.ImportFrom` / `ast.Import` / `ast.Assign` / `ast.AnnAssign`; added AC-3.b (import/alias defense) and AC-3.c (symlink normalization via `is_relative_to`).
- **AC-4** — private `_REGISTRY` replaced with `default_registry.all_probes()`; `startswith` replaced with `is_relative_to`; added AC-4.a (`getsourcefile is None` fails loudly), AC-4.b (bidirectional invariant — wildcard probes MUST live under core), AC-4.c (data-driven strict-xfail predicate).
- **AC-5** — planted-violation matrix expanded from 4 to 10 rows: AC-5.a (basic class), AC-5.b (out-of-scope proof), AC-5.c (recursion proof — nested subdirectory), AC-5.d (nested-class proof), AC-5.e (multi-class-per-file proof), AC-5.f (import re-export proof), AC-5.g (alias-assignment proof), AC-5.h (docstring-not-code proof — AST-vs-regex), AC-5.i (symlink escape proof), AC-5.j (out-of-test evidence — formalized schema + in-suite parser).
- **AC-6** — rewritten from bespoke in-test subprocess call to passive `make check` gate rationale.
- **AC-10** + **AC-11** — added monotonicity and idempotency property invariants (in-line loops, no `hypothesis`; Rule 2 respected).
- **Implementation outline** — full rewrite around `ExpectedProbe` + `Violation` frozen dataclasses; `_REPO_ROOT` anchor via `Path(__file__).resolve().parents[2]`; single-source `_FORBIDDEN_...` derivation; `_no_phase7_probes_registered()` predicate spelled out; `# duplicate-of:` comment discipline; `default_registry.all_probes()` iteration; `is_relative_to` normalization.
- **TDD plan** — updated red/green/refactor steps to match the new AC structure.
- **Files to touch** — expanded to name the required `### AC-5.j evidence` heading schema.
- **Out of scope** — added `TaskId` newtype deferral (design-5) and `iter_probes()` public API follow-up (design-7).
- **Notes for the implementer** — nine bullets rewritten: data-driven xfail transition, bidirectional invariant explanation, single-purpose discipline (unchanged), `getsourcefile None` fail-loud (reversed from original Notes), path portability, rule-of-three refusal, registry-access convention, drift-surfacing (unchanged), vestigial-filename warning, CODEOWNERS anchor (unchanged).

**Not edited** (respect for original scope, Rule 3):
- The story's goal and load-bearing framing.
- The Context section's first two paragraphs (writer-owned narrative).
- The Out-of-scope items about ABC conformance, sub-schemas, registration coverage, and Sigstore.
- The `# duplicate-of:` decision (documented, not extracted).

## Strong dimensions (record for future stories to imitate)

- **Data-driven xfail predicate over prose hand-off** — `_no_phase7_probes_registered()` inspects the registry at collection time; when Phase-7 probes register, the flip is atomic. No implementer-remembers-to-remove-the-marker fragility. Reusable pattern for any fence that lands before its guarded feature.
- **Bidirectional invariant** — task-class-specific ⇒ under `plugins/*/probes/`; wildcard ⇒ under `src/codegenie/probes/`. Catches the "forgot the field" bug (default `["*"]`) that the naive one-direction check misses.
- **Illegal-states-unrepresentable dataclass discipline** — `ExpectedProbe(class_name, expected_path)` makes a cross-contaminated row impossible; `Violation(file, line, kind, name)` with `kind: Literal[...]` closes the discriminator.
- **Rule-2 refusal + `# duplicate-of:` comment** — Rule-of-three triggered but extraction refused (three walkers, three predicates); the comment makes the discipline visible to future readers instead of quietly copy-pasting into a fourth walker.
- **Same-DI-shape as sibling family** — `find_forbidden_class_definitions(roots=[...])` mirrors `_capability_fence.find_violations(roots=[...])`. Planted-fixture tests can point at `tmp_path` without mutating the working tree, sidestepping the `subprocess.run(shell=True)` ban and the "test leakage" trap.

## Provenance / signatures

- Story SHA before validation: checked HEAD of `ci-health/ruff-pin-aiohttp-uncap-vuln-index-exit-code`; story last modified in an earlier commit — unchanged since previous story-writer output.
- Four critic subagents completed 2026-08-14; finding lists archived in the parent conversation transcript (agentIds internal to the run).
- Editor synthesized findings under priority Consistency > Coverage > Test-Quality > Design-Patterns.
