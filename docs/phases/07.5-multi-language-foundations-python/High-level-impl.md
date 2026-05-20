# Phase 7.5 — Multi-language foundations + Python: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-20
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 7.5"

## Executive summary

Phase 7.5 introduces Python as the second target language by addition only, landing one net-new package (`src/codegenie/languages/`) that carries the frozen total-value `LanguagePack` contract and the `register_language()` fan-out. The build is contract-first: the `LanguagePack` value, `DetectionResult` sum type, `markers.py` catalog, and the `register_language`/`validate_pack` kernel must all exist and type-check before either language pack is constructed, and the TypeScript pack must be retrofitted (by reference, `probes_self_registered=True`) before Python so the proof rests on conformance consuming both packs identically. Python capability code — four Layer A/B probes, three dep-graph strategies, a `tree-sitter-python` grammar row, a tree-sitter search adapter, and the `vulnerability-remediation--python--pip` plugin — lands as new files inside existing packages, touching shipped Phase 1–7 code only through the loud, compiler/snapshot-policed edits ADR-0043 sanctions. The phase closes with the `tests/conformance/` tier (which auto-enrolls both registered languages) and the `LanguagePack` contract-snapshot fence, proving the language axis extends by addition rather than merely proving "Python works."

## Order of operations

The sequence is dictated by the **contract-and-registry-before-consumers** discipline. Step 1 lands the foundation edits (newtype/`Literal` extensions) and the `LanguagePack` value, `DetectionResult` sum type, and `markers.py` catalog — every type a downstream consumer references. Step 2 lands the `register_language`/`validate_pack` kernel plus `LanguageRegistry`; a registry kernel must exist before any `@register_language` user, exactly as `@register_probe` precedes every probe. Step 3 retrofits TypeScript as `LanguagePack` #1 *before* Python, because the conformance suite and the registry-drift test both consume `TS_PACK`, and the proof's symmetry requires the retrofit pack to be a real, complete pack — not a paper claim. Steps 4–6 build the Python capability code (probes, dep-graph strategies, search adapter + plugin) as the *plugins* that register into the kernels from Steps 1–3. Step 7 lands the `tests/conformance/` tier once — it auto-enrolls every registered language, so both flow through it — together with the `LanguagePack` contract-snapshot fence. Step 8 wires the integration/e2e proof. The phase's 12 ADRs are already recorded in [`ADRs/`](ADRs/) (written during the architecture stage); each step's done-criteria cite the ADRs they implement.

**Pattern-driven sequencing:** Newtypes (`Language` reused, `PackageManager` +3) and the `LanguagePack` Smart-constructed total value land in Step 1; the `DetectionResult` tagged union lands in Step 1 before the `ProjectDetector` Protocol implementations consume it; the `register_language` registry kernel lands in Step 2 before any `@register_language` user; the `ProjectDetector` hexagonal Port (a `typing.Protocol`) is defined in Step 1, its TypeScript/Python adapters in Steps 3/4; `mypy --strict` + `ruff` + `make fence` + `import-linter` are in Step 1's done criteria and re-checked at every step.

## Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog

**Goal:** Land every net-new *type* the language axis depends on — the frozen total `LanguagePack` value, the `Detected | NotDetected` sum type, the `ProjectDetector` Port, and the addition-only marker catalog — plus the foundation edits that unblock them.

**Features delivered:**
- New package skeleton `src/codegenie/languages/` with `__init__.py` (`__all__` ≤ 6 names) and `pack.py`.
- `LanguagePack` — frozen Pydantic v2 model (`frozen=True, extra="forbid", arbitrary_types_allowed=True`), six required capability fields + `probes_self_registered: bool = False`, derived `package_managers` `@property`.
- `ProjectDetector` `typing.Protocol`; `DetectionResult = Detected | NotDetected` frozen-dataclass sum type.
- `markers.py` — `LANGUAGE_MARKERS: Final[Mapping[Language, tuple[str, ...]]]` catalog (Python + TypeScript marker tuples).
- Foundation loud edits: `SupportedLanguage` Literal `+1` (`"python"`), `PackageManager` Literal `+3` (`"pip"`/`"poetry"`/`"uv"`) in `types/identifiers.py`, `LanguageRegistryError` in `codegenie.errors`.

**Done criteria:**
- [ ] An incomplete `LanguagePack(...)` call is a `mypy --strict` error at the construction site (snippet test: a `mypy`-must-fail fixture).
- [ ] An extra `LanguagePack` field is a `pydantic.ValidationError` (`extra="forbid"` unit test); the value is genuinely frozen (mutation raises).
- [ ] `DetectionResult` exhaustiveness holds — a `match` over it with a missing case is an `assert_never`/`mypy` error.
- [ ] `mypy --strict src/`, `ruff check`, `ruff format --check` all clean; `make fence` green (no `FORBIDDEN_LLM_SDK` rode in); `import-linter` updated for `codegenie.languages`.
- [ ] `LANGUAGE_MARKERS` is the single marker source — no marker tuple duplicated elsewhere in `codegenie.languages`.

**Depends on:** None (foundation step). External prerequisite: none.

**Effort:** M — small surface but every type here is load-bearing and contract-frozen; the `mypy`-must-fail test harness is new machinery.

**Risks specific to this step:** `arbitrary_types_allowed=True` is required for the `type[Probe]`/callable fields — verify Pydantic v2 still enforces `frozen`/`extra="forbid"` under it (it does, but assert it in a test).

## Step 2 — Land the `register_language` / `validate_pack` kernel and `LanguageRegistry`

**Goal:** Build the one privileged registration operation — validate-all-then-commit fan-out into the existing decomposed registries — and the registry every conformance test parameterizes over.

**Features delivered:**
- `LanguageRegistry` — `dict[Language, LanguagePack]` wrapper; `register` (build-then-publish), `get`, `all()` (sorted by `Language`); module-level `default_language_registry`.
- `validate_pack(pack)` — all checks, no writes: totality (Pydantic), grammar-wired (`grammars ⊆ supported_languages()`), adapter-import-resolves, no-shadow.
- `register_language(pack)` — calls `validate_pack`, build-then-publish into `LanguageRegistry`, then Python-only fan-out into `@register_probe` + `@register_dep_graph_strategy`; idempotent per `Language`; emits `language.registered{...}` structured event.
- No-shadow check specified per Gap 1: a `probes_self_registered=False` pack's probe `name` collides iff already present in the live `default_probe_registry`; the probe-name no-shadow check does **not** run for `probes_self_registered=True` packs; the `PackageManager`-key no-shadow check reads `DepGraphRegistry` and runs for *every* pack.

**Done criteria:**
- [ ] A `validate_pack` failure raises `LanguageRegistryError` with **nothing written** — unit test injects a no-shadow-failing pack, asserts all three registries byte-identical to pre-call state.
- [ ] `register_language` is idempotent per `Language` (re-register is a no-op); a duplicate registration of a *different* pack for the same `Language` raises naming both call sites.
- [ ] A `probes_self_registered=True` pack does **not** fan probes out (no `register_probe` calls — would raise `ProbeError`); a `probes_self_registered=False` pack fans all probes + strategies out and they are dispatchable.
- [ ] An un-wired grammar key, an unresolvable `search_adapter_module`, and a probe-name shadow each raise `LanguageRegistryError` at validate time.
- [ ] A Hypothesis property test: for any sequence of distinct packs, `all()` returns them sorted and `get(p.language) == p` for every registered `p`.
- [ ] `mypy --strict` / `ruff` / `make fence` / `import-linter` clean.

**Depends on:** Step 1 (`LanguagePack`, `LanguageRegistryError`). External prerequisite: verify against `codegenie/depgraph/registry.py` whether Node dep-graph strategies are pre-registered (Gap 1 / Open Question 6) and mirror the no-shadow split.

**Effort:** M — the validate-all-then-commit + build-then-publish discipline and the no-shadow asymmetry need careful tests; the kernel itself is small.

**Risks specific to this step:** The mid-fan-out crash residual (a new pack crashing on probe 3 of 5) is contained, not eliminated — land the unit test that asserts the partial state is *detectable*, do not paper over it with a fake rollback.

## Step 3 — Retrofit TypeScript as `LanguagePack` #1 (by reference)

**Goal:** Construct the complete `TS_PACK` value and register it `probes_self_registered=True`, proving the contract fits the *existing* language before Python is built.

**Features delivered:**
- `src/codegenie/languages/packs/__init__.py` — explicit-import collection point (`import .typescript` first).
- `packs/typescript.py` — `TS_PACK` fully enumerated: `language=Language("typescript")`, `grammars=("typescript", "tsx", "javascript")`, `layer_a_probes` = the exact Phase 1 Layer-A probe classes (`LanguageDetectionProbe`, `NodeBuildSystemProbe`, `NodeManifestProbe`, `TestInventoryProbe` — verified against `codegenie/probes/__init__.py`), `dep_graph_strategies`, `search_adapter_module`, `probes_self_registered=True`; calls `register_language(TS_PACK)`.
- A genuine `ProjectDetector` implementation for TypeScript reading `LANGUAGE_MARKERS[Language("typescript")]` (Phase 1 had no `ProjectDetector` — detection was a probe; the detector is a real new object).

**Done criteria:**
- [ ] `register_language(TS_PACK)` succeeds at import; `validate_pack` passes; **no probe fan-out** occurs (the Phase 1 probes are already registered).
- [ ] A registry-drift test: the live `default_probe_registry` contains *at least* the union of all packs' `layer_a_probes` (not equality — Phase 2–7 Layer B–G probes belong to no pack).
- [ ] `default_language_registry.all()` returns exactly `[TS_PACK]` at this step.
- [ ] The full Phase 1–7 Node/TypeScript regression suite (~2,300 tests) runs unchanged and green (G3).
- [ ] `mypy --strict` / `ruff` / `make fence` / `import-linter` clean.

**Depends on:** Steps 1–2. External prerequisite: read `codegenie/probes/__init__.py` Phase 1 imports to enumerate `layer_a_probes` exactly (Gap 2).

**Effort:** S — no new behavior, but the pack must be *completely* enumerated; the drift test must be scoped to "at least the union," not equality.

**Risks specific to this step:** An incomplete `TS_PACK.layer_a_probes` silently weakens the drift test that is itself the retrofit-honesty mitigation (Gap 2) — enumerate the tuple deliberately, do not "retrofit by reference" for the field set.

## Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row

**Goal:** Land the four Python probes (project / build-system / manifest / import-graph) and wire the `tree-sitter-python` grammar so a Python repo can be detected and parsed.

**Features delivered:**
- `tree-sitter-python` PyPI wheel pinned in `pyproject.toml` + `uv.lock`; `+1` `_DISPATCH` row in `grammars/lock.py` (loud edit).
- `src/codegenie/probes/python/` — `PythonProjectProbe` (`tier="base"`, prelude wave, enriches `detected_languages`), `PythonBuildSystemProbe`, `PythonManifestProbe` (`tier="task_specific"`, `applies_to_languages=["python"]`), `PythonImportGraphProbe` (Layer B).
- A real Python `ProjectDetector` reading `LANGUAGE_MARKERS[Language("python")]`: `Detected(confidence="high")` on a real manifest, `Detected(confidence="low")` for a bare `*.py` tree, `NotDetected` otherwise.
- Hard caps before parse — byte / depth / entry caps + per-probe timeout reusing Phase 1 `SizeCapExceeded`/`DepthCapExceeded`/`SymlinkRefusedError`; `_WARNING_IDS` (`python.manifest_oversized`, `python.lockfile_truncated`, `python.setup_py_not_static`).
- `setup.py`/`setup.cfg` parsed structurally (tree-sitter / INI), **never executed**.
- Python probe sub-schemas under `src/codegenie/schema/probes/python_*.schema.json` (`additionalProperties: false`), `$ref`-wired into the envelope's `properties.probes`.
- `+1` import line in `codegenie/probes/__init__.py` (loud edit).

**Done criteria:**
- [ ] Each probe runs against in-memory fixtures (detected / not-detected / malformed `pyproject.toml` / missing lockfile); a malformed manifest yields a structured-error slice — the probe never crashes.
- [ ] An AST test forbids `exec` / `eval` / `__import__` / `importlib`-of-a-repo-file anywhere in `src/codegenie/probes/python/` (G6).
- [ ] An oversized (>5 MiB) and a billion-laughs lockfile are rejected *before* parse with a structured warning — no OOM, no hang (G7).
- [ ] `_WARNING_IDS` validated at import (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`); each probe declares `declared_inputs` globs tightly so the cache invalidates surgically.
- [ ] `language_for("python")` loads the grammar lazily; `make fence` asserts the wheel pin is present and no `FORBIDDEN_LLM_SDK` rode in.
- [ ] `mypy --strict` / `ruff` / `import-linter` clean.

**Depends on:** Steps 1–2 (types + kernel). External prerequisite: `tree-sitter-python` wheel available on PyPI.

**Effort:** L — four probes, structural `setup.py` parsing, four sub-schemas, and the full adversarial cap matrix; the largest single step.

**Risks specific to this step:** `setup.py` structural parsing must never reach `exec` — the AST test is the gate; treat a parse failure on a hostile `setup.py` as a `confidence="low"` fact, not an error.

## Step 5 — Build the Python dep-graph strategies (pip / poetry / uv)

**Goal:** Land three concrete pure-parse dep-graph strategies and the `tests/fence/test_depgraph_purity.py` AST fence that proves they perform zero I/O.

**Features delivered:**
- `src/codegenie/depgraph/python/` — `pip.py` (`requirements.txt` directive-language parser), `poetry.py` (`poetry.lock` TOML), `uv.py` (`uv.lock` TOML); registered via `@register_dep_graph_strategy` for keys `"pip"`/`"poetry"`/`"uv"`.
- `requirements.txt` directive classifier — every non-pinned-dependency directive recorded as a *fact*, never acted on: `-e .` → `editable_install`; `git+...` → `vcs_source`; `--index-url`/`--extra-index-url` → `IndexOverride{url_host}` (host only, **never honored**); `-r <path>` followed only inside the repo root else `out_of_tree_include`; unknown directive → `unknown_directive` (fail closed, never silently dropped).
- Typed fact dataclasses `UnresolvedDependency` and `IndexOverride`; byte+depth caps before parse on all lockfile formats.
- `tests/fence/test_depgraph_purity.py` — AST-walk over `src/codegenie/depgraph/python/` forbidding `urllib`/`requests`/`http`/`socket`/`subprocess`.

**Done criteria:**
- [ ] `test_depgraph_purity.py` is green: no network/exec import or call in `depgraph/python/` (G5).
- [ ] An adversarial `requirements.txt` corpus (`-e .`, `git+https://`, `--index-url http://attacker/`, `-r /etc/passwd`, `-r ../../../etc/passwd`, an unknown directive) — a network monitor asserts **zero outbound connections**, a subprocess monitor asserts **zero spawns**; each hostile directive maps to the correct typed fact.
- [ ] `IndexOverride` stores host only — the full attacker-controlled URL is never persisted.
- [ ] Each strategy resolves a minimal valid lockfile to a `networkx.DiGraph`; a VCS-only repo yields a near-empty graph with `confidence="low"` and explicit unresolved reasons.
- [ ] `ALLOWED_BINARIES` closed-set regression test: `pip`/`poetry`/`uv`/`scip-python` are **not** present (G8).
- [ ] `mypy --strict` / `ruff` / `import-linter` clean.

**Depends on:** Steps 1–2 (`PackageManager` Literal, kernel); Step 4 (cap machinery reuse pattern established for Python).

**Effort:** M — three parsers plus the directive corpus and purity fence; the `requirements.txt` directive language is the trickiest surface.

**Risks specific to this step:** A future pip directive must hit the default-deny branch, not be silently dropped — the unknown-directive test is the teeth.

## Step 6 — Build the Python search adapter and the `vulnerability-remediation--python--pip` plugin

**Goal:** Land the tree-sitter-backed ADR-0032 search adapters and the Python vulnerability-remediation plugin so the `(vuln, python, pip)` tuple resolves to a real diff.

**Features delivered:**
- A tree-sitter-backed `ImportGraphAdapter` (mandatory) + `DepGraphAdapter` + `TestInventoryAdapter`; `confidence() -> float` per ADR-0032 as written (no invented amendment).
- `plugins/vulnerability-remediation--python--pip/` — `plugin.yaml` (`extends` the universal base, `contributes.adapters` wiring the Python adapters), `adapters/python_tree_sitter.py`.
- The plugin resolves from the `(vuln, python, pip)` tuple.

**Done criteria:**
- [ ] The plugin manifest validates via Pydantic and the `extends` chain resolves to the universal base.
- [ ] The search adapter against a fixture returns a non-empty, non-degenerate result for a known query (not a stub).
- [ ] An integration test: the `vulnerability-remediation--python--pip` plugin produces a real diff on a vulnerable Python fixture under `tests/golden/languages/python/` (G10).
- [ ] No new binary entered `ALLOWED_BINARIES` (`scip-python` deferred — tree-sitter-first).
- [ ] `mypy --strict` / `ruff` / `import-linter` clean.

**Depends on:** Steps 4–5 (Python probes + dep-graph for the plugin to consume). External prerequisite: the universal base plugin from Phase 7 exists.

**Effort:** M — adapter implementations plus plugin wiring; the integration test against a real vulnerable fixture is the load-bearing assertion.

**Risks specific to this step:** A stub adapter would pass `mypy` and a naive test — the fixture must have ≥ 1 cross-file reference and ≥ 1 dep edge so the not-a-stub assertion has teeth (this carries into Step 7's conformance).

## Step 7 — Land the `tests/conformance/` tier and the `LanguagePack` contract-snapshot fence

**Goal:** Build the parameterized conformance suite that auto-enrolls every registered language and the contract+snapshot fence — the category-based extension-by-addition fence.

**Features delivered:**
- `tests/conformance/test_language_conformance.py` — parameterized over `default_language_registry.all()` with `Language` as the `pytest.param` id; session-scoped per-language gather fixture.
- Per-language assertions: `test_grammar_loads`, `test_detector_detects_own_fixture` (`Detected`, `confidence="high"`), `test_layer_a_probes_produce_nonempty_slices`, `test_dep_graph_strategy_resolves`, `test_search_adapter_is_not_a_stub`, `test_golden_matches`, and `test_language_probes_actually_dispatched` (Gap 3 — asserts every `pack.layer_a_probes` probe appears in the run's `coordinator.dispatch.order` audit event).
- Collection-completeness guard: top-of-module `assert len(default_language_registry.all()) == EXPECTED_LANGUAGE_COUNT` (= 2).
- Mandatory per-language golden fixtures under `tests/golden/languages/{typescript,python}/` — one clean fixture per language + the adversarial set (hostile `requirements.txt`, oversized/billion-laughs lockfiles, hostile `setup.py`, bidi/zero-width package name) + a polyglot fixture; a golden-regen idempotence test; a fixture-shape meta-test (≥ 1 cross-file ref + ≥ 1 dep edge).
- `packs/__init__.py` extended with `import .python` (Python pack now constructed and registered — `PYTHON_PACK`).
- `tests/fence/test_language_pack_contract.py` + `tests/fence/snapshots/language_pack_contract.v1.json` — snapshot pinning the `LanguagePack` field set + types.

**Done criteria:**
- [ ] `tests/conformance/` is green for **both** registered languages; a deliberate stub-adapter negative test fails conformance (G4).
- [ ] `test_language_probes_actually_dispatched` is green; a negative unit test — a Python probe with a typo'd `applies_to_languages` (`["py"]`) — makes the dispatch-order assertion fail, proving teeth (Gap 3, Rule 9).
- [ ] The collection-completeness guard fails loudly if a pack module fails to import (negative test).
- [ ] A planted `LanguagePack` field-add turns `test_language_pack_contract.py` red; a planted Node-probe-body change turns the G3 regression gate red (G9 — both planted-edit levels).
- [ ] Adversarial fixtures (oversized lockfile, hostile `setup.py`, bidi package name) are conformance cases — "fails closed" is part of *passing*.
- [ ] The conformance session-fixture gather completes within `make check`'s wall-clock envelope; no `asyncio.gather` of fixture builds, no `pytest-xdist`.
- [ ] A `sys.modules` fence: after a Node-only gather, `tree_sitter_python` is absent from `sys.modules` (G11).

**Depends on:** Steps 3–6 (both packs and all Python capabilities must exist before conformance enrolls them).

**Effort:** L — the conformance tier is new test infrastructure, the fixture portfolio is broad (clean + adversarial + polyglot per language), and the dispatch-order assertion needs the audit-event plumbing.

**Risks specific to this step:** The fixture must defeat a stub adapter yet stay small enough for the session gather to fit `make check` (Open Question 1) — size the fixture deliberately and assert the shape with the meta-test.

## Step 8 — Wire the e2e proof and close the phase gate

**Goal:** Add the e2e slice row exercising the full Python path and bring `make check` + CI fully green.

**Features delivered:**
- A row in the table-driven `tests/e2e/` slice harness: `gather → (vuln, python, pip) plugin resolution → diff` against the vulnerable Python fixture.
- `import-linter` contracts finalized for all new Python sub-packages; `make fence` extended for the `tree-sitter-python` pin.
- `phase-arch-design.md`'s ADR table reconciled against the 12 ADRs already in [`ADRs/`](ADRs/) (no new ADRs — they were written at architecture time).

**Done criteria:**
- [ ] The e2e row is green — a real diff is produced end to end against the vulnerable Python fixture.
- [ ] `make check` (lint → typecheck → test → fence) is fully green including the new conformance and e2e slices.
- [ ] CI matrix (Python 3.11 / 3.12 × `ubuntu-24.04`) reproduces `make check` green.
- [ ] Each step's done-criteria reference the governing ADR (0001–0012); no ADR is orphaned.

**Depends on:** Steps 1–7 (all capability and conformance work complete).

**Effort:** S — wiring only; no new runtime code beyond the e2e harness row.

## Exit-criteria mapping

| Exit criterion (verbatim or close) | Step(s) |
|---|---|
| Python and TypeScript both run from the same gather + plugin orchestration | 3, 4, 6, 7 (dispatch-order assertion), 8 (e2e) |
| The Node/TypeScript regression suite is unchanged and green | 3, 7 (planted Node-edit gate), 8 |
| Every registered language passes `tests/conformance/` | 7 |
| An incomplete `LanguagePack` fails `mypy --strict` | 1 |
| The category-based fence rejects a planted silent edit | 7 (`test_language_pack_contract.py` + G3 gate) |
| The `vulnerability-remediation--python--pip` plugin produces a real diff on a vulnerable Python fixture | 6, 8 (e2e) |
| `tests/conformance/` tier — parameterized, auto-enrolls every language; capability passing `mypy` but broken fails conformance | 7 |
| Mandatory per-language golden fixtures under `tests/golden/languages/{language}/` | 7 |
| ADR-0043 discipline reframe — contract+snapshot test replaces byte-edit allowlist | 7 (`test_language_pack_contract.py` fence); recorded in phase-ADR-0012 |

## Implementation-level risks

- **TypeScript retrofit is under-specified beyond two fields (Gap 2).** *Signal:* the registry-drift test in Step 3 fails, or `TS_PACK.layer_a_probes` is left partial. *What to do:* Step 3's first task is to read `codegenie/probes/__init__.py` and enumerate the Phase 1 Layer-A probe classes exactly; scope the drift test to "at least the union," never equality (Phase 2–7 Layer B–G probes belong to no pack).
- **The no-shadow check reads the wrong source set (Gap 1 / Open Question 6).** *Signal:* a Python probe colliding with a Phase 2–7 Layer-D probe slips through, or a false positive blocks a clean pack. *What to do:* Step 2 must read `codegenie/depgraph/registry.py` and the Node plugin manifest to confirm whether Node dep-graph strategies are pre-registered; specify the probe-name check against the live `default_probe_registry` and gate it on `probes_self_registered=False`; record the decision in phase-ADR-0002.
- **Registered-but-never-dispatched Python probe (Gap 3).** *Signal:* every isolated conformance assertion passes but the probe never runs in a real gather (e.g. `applies_to_languages=["py"]`). *What to do:* Step 7 must land `test_language_probes_actually_dispatched` reading the `coordinator.dispatch.order` audit event, plus the negative typo test that proves it has teeth — do not let the story-writer collapse it into the weaker isolated assertions.
- **Stub adapter passes a thin fixture.** *Signal:* `test_search_adapter_is_not_a_stub` is green against a fixture with no cross-file references. *What to do:* Step 7's fixture-shape meta-test must assert ≥ 1 cross-file ref + ≥ 1 dep edge per fixture before the not-a-stub assertion is trusted.
- **`setup.py` structural parsing drifts toward execution.** *Signal:* a tree-sitter parse failure on a hostile `setup.py` is handled by a fallback that imports or `exec`s the file. *What to do:* Step 4's AST test forbids `exec`/`eval`/`importlib`-of-repo-file; a parse failure must yield a `confidence="low"` "not statically analyzable" fact, never a fallback execution.
- **Conformance session gather blows the `make check` envelope.** *Signal:* CI wall-clock for `tests/conformance/` grows past the existing budget. *What to do:* Step 7 sizes the per-language fixture deliberately (small but stub-defeating), uses one session-scoped gather per language, and forbids `asyncio.gather` of fixture builds and `pytest-xdist`.

## What's next — handoff to Phase 8

- **New contracts on disk.** The `LanguagePack` contract (`Provisional Accepted`, `Review trigger: third language pack`), `register_language`, the `DetectionResult` sum type, the `LANGUAGE_MARKERS` catalog, and the `UnresolvedDependency`/`IndexOverride` Python dep-graph fact types — the seam every Phase 8+ target language registers through.
- **New CI gates.** The `tests/conformance/` tier (every future language auto-enrolls — only `EXPECTED_LANGUAGE_COUNT` needs a loud `+1`), the `tests/golden/languages/{language}/` per-language golden discipline, and `tests/fence/test_language_pack_contract.py` — the contract+snapshot model for every future frozen surface (ADR-0043 commitment 3; Phase 7's byte-edit allowlist is now the last).
- **State Phase 8 can assume.** `repo-context.yaml` slices now carry a per-slice `language` tag — Phase 8's Planner routes per-language without re-detecting. The Python probe sub-schemas are `$ref`-wired into the envelope and read through the existing machinery.
- **Implicit guarantees.** A registered language cannot be partially registered (`mypy` error), cannot be semantically half-broken and still merge (`tests/conformance/` blocks it), and cannot be silently un-enrolled (the collection-completeness guard). The coordinator, sanitizer, and writer are language-agnostic — Phase 8 adds languages without touching them.
- **The known caveat.** The `LanguagePack` six-field contract was frozen on two near-isomorphic ecosystems; Java/Maven (classpath, compiled artifacts, POM inheritance) will likely force a `LanguagePack` field-add — expected and loud (the contract-snapshot fence goes red, the `Review trigger` fires), not a surprise.
- **Deferred fast-follows Phase 8 may schedule.** The `scip-python` `ScipAdapter` (needs an `ALLOWED_BINARIES` amendment under Phase 2 omnibus ADR-0001) and the `distroless-migration--python--pip` plugin — both deliberately out of Phase 7.5 scope.
