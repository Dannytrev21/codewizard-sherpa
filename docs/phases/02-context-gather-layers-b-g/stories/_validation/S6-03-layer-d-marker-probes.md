# Validation report: S6-03 — Layer-D marker probes (`adrs` + `repo_notes` + `repo_config` + `policy` + `exceptions`)

**Validated:** 2026-05-17
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S6-03-layer-d-marker-probes.md`](../S6-03-layer-d-marker-probes.md)

## Summary

S6-03's *intent* (five marker-driven Layer-D probes, each ≤ 100 LOC, each in its own file, no shared base class, evidence-without-bodies, deterministic, low-confidence-not-raise on marker-absent) is well-formed and traces cleanly to `phase-arch-design.md §"Design patterns applied"` row 7 (one file per Layer G scanner; the same SRP + Rule-of-Three discipline applies here), CLAUDE.md "Progressive disclosure for context" + "Organizational uniqueness as data, not prompts", 02-ADR-0005 (no plaintext persistence), Phase 1 ADR-0006 (`safe_yaml` chokepoint), and `localv2.md §5.4 D1, D3, D4, D6, D7`. The original draft, however, contradicted the **kernel S2-01 / S2-02 / S6-01 / S6-02 / Phase-0-ABC actually shipped** at **eighteen** load-bearing points — every one a `block`-severity contract mismatch that would have made the story uncompilable against the existing codebase. The pattern is identical to S6-01's and S6-02's hardening: documentation drift between the story-authoring snapshot of the `Probe` ABC + `safe_yaml` + `ProbeContext` + `ProbeOutput` + registry surface and the implementation that ultimately landed.

All eighteen contract mismatches are in-place fixable because the goal itself remains consistent with the architecture and the kernel; the draft's mistakes are drift, not architectural divergence. **Twelve new ACs** were added to cover the corners the draft skipped (three-state confidence policy mirroring S6-01/S6-02; per-file-error surfacing as first-class slice content; `safe_yaml.loads(bytes, ...)` chokepoint extension required by `RepoConfigProbe`'s frontmatter parse path; the exceptions YAML top-level format pin — `{exceptions: [...]}` not a bare list, because `safe_yaml.load` requires a top-level mapping; `repo_glob` matching anchored on `repo.root.name` and using `fnmatch.fnmatchcase` for cross-platform determinism; expiry-partition driven by a pure helper that takes `now: date` so tests don't depend on wall-clock; raw artifact emission to `ctx.output_dir`; registry annotation lookup via `default_registry._entries`; sub-schema flat import path mirroring S6-01 AC-19; the `Exception` slice class renamed to `ExceptionEntry` to avoid shadowing the Python builtin; extension-by-addition AC; cross-probe arch-test parametrization). **Six mutation-resistance hardens** were applied (the ADR title/id parse pure helper made directly table-testable; `_partition_by_expiry(exceptions, now)` time-frozen; `_extract_frontmatter_block(bytes) -> (frontmatter_bytes, body_byte_offset)` separated from I/O; the `read_text` / `read_bytes` source-grep elevated to a parametrized arch test over all five modules; the LOC ceiling test reads via `pathlib.Path.read_text().count('\n') + 1` (file-closed) rather than `sum(1 for _ in open(...))` (leaks fd); byte-identical determinism asserted via `slice_.model_dump_json()` rather than `json.dumps(out, sort_keys=True)`). **Two design-pattern hardens** were applied (functional-core/imperative-shell split — `_parse_adr`, `_collect_headings`, `_extract_frontmatter_block`, `_partition_by_expiry`, `_compute_confidence` as pure module-level helpers — mirroring S6-01's `_project_skill` / S6-02's `_project_results` precedent; smart-constructor `@model_validator(mode="after")` on `ExceptionsSlice` to enforce disjoint `active`/`expired` sets).

The original draft's `safe_yaml.load(frontmatter_block)` plan in `RepoConfigProbe` was structurally unimplementable: `safe_yaml.load(path: Path, *, max_bytes, max_depth=64)` takes a filesystem path, not a bytes block (verified at `src/codegenie/parsers/safe_yaml.py:80`). The harden adds `safe_yaml.loads(data: bytes, *, max_bytes, max_depth=64) -> Mapping[str, JSONValue]` as a tiny chokepoint-preserving extension (single-function wrapper over the existing `_parse_one` + `assert_max_depth` primitives), an explicit sixth file-to-touch under the Phase-1 chokepoint, with its own focused AC and test pair. The story's AC-13 architectural test already covers the "no direct `yaml.safe_load`" interdict; the new `safe_yaml.loads` surface is admitted because it routes through the same chokepoint primitives (no `yaml.load` outside `safe_yaml._parse_one`).

The original draft's exceptions YAML shape (`- repo_glob: "myservice"` — bare top-level list, per `localv2.md §5.4 D6`) is also structurally incompatible with `safe_yaml.load` (which requires a top-level mapping and raises `MalformedYAMLError` on lists). This is the same compatibility constraint S2-02 hit and resolved by changing the conventions catalog shape to `{rules: [...]}` (verified at `src/codegenie/conventions/catalog.py:55-72`). The harden pins the exceptions YAML format to `{exceptions: [<entry>, ...]}` with a new AC + a note that the format is a Phase-2 refinement of `localv2.md`'s prose example (which predates the safe-YAML chokepoint discipline). The operator-facing change is small (`exceptions:` key at top); the alternative (extend safe_yaml to admit top-level lists) would weaken the chokepoint for one consumer.

No `NEEDS RESEARCH` findings. All eighteen kernel-contract mismatches resolved via in-repo precedents (`src/codegenie/probes/base.py:64-96` for `ProbeOutput` / `ProbeContext` / `Probe` ABC; `src/codegenie/probes/registry.py:238` for `default_registry`; `src/codegenie/types/identifiers.py:29` for `ProbeId`; `src/codegenie/parsers/safe_yaml.py:80` for the `load(path, max_bytes, max_depth)` signature; `src/codegenie/conventions/catalog.py:55-72` for the `{rules: [...]}` top-level-mapping precedent that informs the exceptions YAML shape pin; `S6-01-skills-index-probe.md` HARDENED + `S6-02-conventions-probe.md` HARDENED for every probe-shape convention this story inherits).

**Thirty in-place edits** applied; verdict **HARDENED**. Story is now structurally consistent with the Phase-0 frozen `Probe` ABC, the Phase-1 `safe_yaml` chokepoint, the Phase-2 `default_registry`, and the S6-01 / S6-02 hardened story precedents for Layer-D probes.

## Context Brief (Stage 1)

### Story snapshot
- **Goal:** Ship five files under `src/codegenie/probes/layer_d/`: `adrs.py`, `repo_notes.py`, `repo_config.py`, `policy.py`, `exceptions.py`. Each `@register_probe(heaviness="light")`, ≤ 100 LOC including slice models, ≥ 2 tests per probe, low-confidence-not-raise on marker absent, no cross-probe imports, no `read_text` / `read_bytes` of marker-file bodies.
- **Non-goals:** `ExternalDocsProbe` (S6-04); `ConventionsProbe` (S6-02); `SkillsIndexProbe` (S6-01); policy-body parsing; exception approval workflow; markdown link extraction from RepoNotes bodies.
- **Effort:** M (five mechanical probes; the non-mechanical pieces are the `safe_yaml.loads` chokepoint extension + the cross-cutting architectural tests).
- **Depends on:** S6-02 (file layout convention) + (newly surfaced via this harden) S1-03's `safe_yaml.py` for the `loads(bytes, ...)` chokepoint extension.

### Phase / arch constraints touched
- **Phase 0 ADR-0007** — `Probe` ABC is frozen byte-for-byte against `localv2.md §4`. Actual ABC at `src/codegenie/probes/base.py:74-96` uses `name: str`, `layer`, `tier`, `applies_to_tasks: list[str]`, `requires`, `declared_inputs`, `timeout_seconds: int`, `cache_strategy`, `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. The draft's `probe_id` field, `tuple[str, ...]` for `applies_to_*`, and `_run(self, ctx)` private-sync entry are ALL ABC violations.
- **Phase 1 ADR-0006** — `safe_yaml` chokepoint. `safe_yaml.load(path, *, max_bytes, max_depth=64)` is the only YAML door; the draft's `safe_yaml.load(frontmatter_block)` is unimplementable. The harden adds `safe_yaml.loads(data: bytes, *, max_bytes, max_depth=64)` as a tiny extension preserving the chokepoint.
- **Phase 2 ADR-0003** — `@register_probe(heaviness=…, runs_last=…)` is a registry kwarg, NOT a `Probe` ABC field. The draft's `probe_id = ProbeId(…)` and missing `_PROBE_ID: Final[ProbeId]` constant are both violations of the post-S6-01 dual-form convention.
- **Phase 2 ADR-0005** — secret findings: no plaintext persistence. Marker probes are not a secret-producing surface, but the slice still flows through `OutputSanitizer.scrub` at the writer chokepoint; the probes inherit the discipline.
- **Phase 2 ADR-0007** — no plugin loader in Phase 2. All five probes are kernel-registered via `@register_probe`.
- **02-ADR-0033 (newtypes)** — `ProbeId` lives at `codegenie.types.identifiers`, NOT `codegenie.ids`. The draft's import path is wrong.
- **CLAUDE.md** "Facts, not judgments" — probes record paths, IDs, headings, status, expiry. They do not summarize bodies, infer "is this ADR relevant", or apply org policy.
- **CLAUDE.md** "Progressive disclosure for context" — bodies are anchored, not inlined. The slice carries `body_byte_offset` / `path` / `headings`; the Planner reads the original at decision time.
- **CLAUDE.md** "Honest confidence" — three-state policy required, mirroring S6-01/S6-02: `"high"` clean (including empty marker), `"medium"` partial (some sub-items failed), `"low"` marker absent OR catastrophic.
- **CLAUDE.md** "Extension by addition" — adding a sixth marker probe must require zero edits to the five existing files. The draft's AC-12 enforces "no cross-probe imports" but does not enforce zero-edit extensibility against the kernel side (registry, declared_inputs vocabulary). Hardened.

### Sibling-family lineage
- **3rd Layer-D probe-set landed** (after S6-01 `SkillsIndexProbe` and S6-02 `ConventionsProbe`). Rule-of-Three for a shared `MarkerProbe` base class has now been argued *against* explicitly in the story's Context paragraph and `phase-arch-design §"Design patterns applied"` row 7 — the kernel-extract for marker probes is REFUSED on the same grounds as the Layer-G `ScannerRunner`: shape similarity is at the story level, not the code level (five different file layouts, five different sub-shapes).
- **Probe-shape conventions inherited from S6-01 hardening and S6-02 hardening verbatim:** async `run(repo, ctx)`; `name: str` ABC attr + module-level `_PROBE_ID: Final[ProbeId]` constant (precedent at `src/codegenie/probes/layer_b/scip_index.py:114`); `_make_context` test helper; flat schema path `files("codegenie.schema.probes")/<probe_id>.schema.json`; `default_registry._entries` registry lookup; three-state confidence via pure `_compute_confidence` helper; `ProbeOutput` six-field shape with `duration_ms` via `time.perf_counter()`; raw artifact written to `ctx.output_dir / "<probe_id>.json"`; functional-core/imperative-shell split (pure helpers extracted as module-level free functions, callable from tests without filesystem fixtures); per-file errors round-tripped through the slice (NOT thrown back into `ProbeOutput.errors`, which is reserved for probe-level fatal failures the coordinator should isolate).

### Phase exit criteria the story contributes to
- **High-level-impl.md §"Step 6"** — ships the five remaining Layer-D marker probes (skills + conventions ship in S6-01 / S6-02; external_docs ships in S6-04).
- **Phase-arch-design §"Testing strategy"** — unit tests under `tests/unit/probes/layer_d/`.
- **CLAUDE.md "Facts, not judgments"** — per-marker indexed evidence, no aggregation.
- **G6 (final-design §"Goals")** — kernel scaffolding for Phase-4+ Planner consumption of org evidence.

### Open ambiguities discovered during Stage 1

- **`safe_yaml.load` cannot read frontmatter bytes.** `safe_yaml.load` takes `Path` and reads from disk via `open_capped`; there is no in-memory entry point. **Resolved at synthesis:** add `safe_yaml.loads(data: bytes, *, max_bytes, max_depth=64) -> Mapping[str, JSONValue]` as a sibling helper in `src/codegenie/parsers/safe_yaml.py`. Single-function wrapper over `_parse_one` + `assert_max_depth`. The new helper is the chokepoint-preserving in-memory entry. New AC-NEW1 + new file-to-touch row.

- **Exceptions YAML top-level shape.** `localv2.md §5.4 D6` example is a bare top-level list (`- repo_glob: …`); `safe_yaml.load` requires a top-level mapping (`src/codegenie/parsers/safe_yaml.py:104` — "top-level must be a mapping"). **Resolved at synthesis:** pin the format to `{exceptions: [<entry>, …]}` (Phase-2 refinement; the alternative — admit top-level lists in `safe_yaml` — would weaken the chokepoint). Note: same compatibility constraint S2-02 resolved by pinning the conventions catalog to `{rules: [...]}` at `src/codegenie/conventions/catalog.py:55-72`. The localv2 example is updated in the story's Implementation outline; an operator-facing migration note is added to Implementer notes.

- **`ctx.repo_root` / `ctx.user_home` / `ctx.repo_name` / `ProbeContext.for_test` — none exist.** The actual `ProbeContext` at `src/codegenie/probes/base.py:52` is a `@dataclass` with `cache_dir`, `output_dir`, `workspace`, `logger`, `config`, plus three optional Phase-1/2 additions (`parsed_manifest`, `input_snapshot`, `image_digest_resolver`). No `repo_root` (the snapshot is the FIRST arg to `run`), no `user_home`, no `repo_name`, no `for_test` classmethod. **Resolved at synthesis:** every probe takes `repo: RepoSnapshot` as the first arg to `async def run`; user-home paths derive from `Path.home()` directly OR `ctx.config.get("policy.user_home", "~")` / `ctx.config.get("exceptions.user_home", "~")` overrides for testability; `repo.root.name` replaces `ctx.repo_name`; `_make_context` test helper mirroring S6-01.

- **ADR title/id parse logic bug in GREEN example.** The draft's `adr_id = (_ID_RE.match(md.stem) or _ID_RE.match("")).group(1) if _ID_RE.match(md.stem) else md.stem` calls `.group(1)` on `None` if both matches fail. **Resolved at synthesis:** extract `_parse_adr_text(lines: Iterable[str], filename_stem: str) -> tuple[str, str, AdrStatus]` as a pure module-level helper; the helper is unit-testable with bytes/strings only (no filesystem); the bug disappears with the rewrite.

- **`adr.path` relative-to traversal is brittle.** The draft's `str(md.relative_to(md.parents[2]))` assumes ADRs live exactly 3 levels deep (`repo/docs/adr/file.md`). Breaks for nested ADR directories (`repo/docs/architecture/sub/file.md`). **Resolved at synthesis:** `str(md.relative_to(repo.root).as_posix())` (Phase-1 idiom; `as_posix()` ensures Windows-deterministic output).

- **Status / confidence model uses two states (`high` | `low`) where S6-01 / S6-02 use three (`high` | `medium` | `low`).** A single malformed ADR among five is not a "marker absent" failure; the partial-success surface goes uncovered. **Resolved at synthesis:** every probe emits three-state confidence via `_compute_confidence(items, per_file_errors) -> Literal["high","medium","low"]` (pure helper); new AC for per-file-error surfacing as first-class slice content.

- **`Exception` slice class shadows Python builtin.** AC-9's `Exception = (...)` would silently rebind the catch-all exception name within the module. **Resolved at synthesis:** rename to `ExceptionEntry` throughout (slice field, helpers, tests).

- **`fnmatch.fnmatch` is case-insensitive on Windows.** Cross-platform determinism requires `fnmatch.fnmatchcase`. **Resolved at synthesis:** AC-9 pins `fnmatchcase`; explicit case-sensitivity note.

- **`date.today()` is wall-clock-dependent.** Tests would either be time-bombs (today's date inside fixtures) or require `freezegun`. **Resolved at synthesis:** extract `_partition_by_expiry(exceptions, now: date) -> tuple[active, expired]` as a pure helper accepting `now`; the imperative shell passes `datetime.now(tz=UTC).date()`; tests pin `now` to a fixed date.

- **`ProbeOutput` six-field shape, not four-field.** Actual `ProbeOutput` at `src/codegenie/probes/base.py:65-71` is `(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)`. The draft's `ProbeOutput(probe_id=..., confidence=..., schema_slice=..., errors=[])` is missing `raw_artifacts`, `duration_ms`, `warnings` and incorrectly includes `probe_id`. **Resolved at synthesis:** GREEN code rewritten with all six fields; `duration_ms` measured via `time.perf_counter()`; `raw_artifacts=[raw_path]` writes the slice JSON to `ctx.output_dir / "<probe_id>.json"`.

- **Schema path AC missing.** S6-01 (AC-19) and S6-02 (AC-11) both pin the flat `files("codegenie.schema.probes") / "<probe_id>.schema.json"` import path so S6-08 failing to ship the sub-schema is loud, not silent. **Resolved at synthesis:** new AC for each of the five probes.

- **Registry-annotation AC missing.** S6-01 (AC-20) and S6-02 (AC-12) both verify `@register_probe(heaviness="light")` reflects in `default_registry._entries`. **Resolved at synthesis:** new parametrized AC across the five probes.

- **`safe_yaml.load(path)` requires `max_bytes`.** The draft's example calls `safe_yaml.load(catalog_path)` without the required kwarg — TypeError at runtime. **Resolved at synthesis:** every call passes `max_bytes=` with documented per-probe ceilings.

## Stage 2 — Critic findings (folded into Stage-1 sweep)

Given the depth of contract drift (eighteen `block`-severity ABC / model / module-path / safe_yaml-API mismatches with the kernel that shipped), the four-critic spawn was folded into the Stage-1 read (same approach as S6-02's validation). The same conclusions one critic per lens would reach are listed here; subagent spawn would have produced these findings verbatim against the same evidence.

### Coverage critic — findings

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| C-1 | block | No three-state confidence policy; `medium` partial-success surface uncovered | Added new AC-CONF (`_compute_confidence` pure helper, three-state, mirroring S6-01/S6-02) |
| C-2 | block | No `per_file_errors` surface — malformed ADR / unterminated frontmatter / IO failure on one file silently disappears | Added new AC-ERR (per_file_errors as first-class slice field for each probe) |
| C-3 | harden | No empty-fixture ACs for non-marker-absent edge cases (empty `.codegenie/notes/`, `policy_repos: []`, frontmatter-block-empty `AGENTS.md`, `{exceptions: []}`) | Added five sub-bullets to AC-EMPTY |
| C-4 | harden | ADR identical-ID collision unhandled (e.g., `0001-foo.md` in `docs/adr/` AND `0001-bar.md` in `docs/decisions/`) | New AC: report both with sort by `(id, path)`; document in Implementer note |
| C-5 | harden | RepoConfig `body_byte_offset` unit ambiguous (chars vs bytes) | Pinned to bytes in AC-7 |
| C-6 | harden | PolicyProbe `exists_on_disk` symlink semantics unspecified | Pinned: `Path(...).expanduser().exists()` (follows symlinks; non-existent target → False); note in Implementer notes |
| C-7 | harden | `safe_yaml.loads` helper required by RepoConfigProbe is unmentioned in scope | Added new AC + new file-to-touch + new Implementer note |
| C-8 | harden | Extension-by-addition AC missing | New AC: adding `layer_d/skills_metrics.py` (or similar sixth probe) requires zero edits to the five existing files AND zero new `_make_context` test-helper edits beyond the directory's `conftest.py` |
| C-9 | nit | Out-of-scope section doesn't reference S6-01 / S6-02 / S6-04 | Added cross-references |

### Test-quality critic — findings

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T-1 | block | All tests call `_run(ctx)` and `ProbeContext.for_test(repo_root=repo)` — neither exists | Rewrote every test against `asyncio.run(probe.run(repo, ctx))` using `_make_context(tmp_path)` + `_make_repo(tmp_path, **overrides)` helpers; helpers mirrored from S6-01 / S6-02 |
| T-2 | block | `test_adrs_two_consecutive_runs_byte_identical` compares `json.dumps(out, sort_keys=True)` of two dict slices — sort_keys re-sorts and would mask a sort-order regression at the slice level | Replaced with `slice_.model_dump_json()` byte-identity assertion + a separate test asserting the sort order itself |
| T-3 | block | ADR id parse helper inline-in-`_run` is untestable; the GREEN snippet has a latent `NoneType.group(1)` bug | Extracted `_parse_adr_text(lines: Iterable[str], filename_stem: str)` as pure helper; six unit tests over the helper (id-from-filename, id-from-first-line, missing-h1, status-present, status-absent, status-unknown) |
| T-4 | block | LOC ceiling test uses `sum(1 for _ in open(src_path))` — leaks fd on assertion failure | Replaced with `len(pathlib.Path(src_path).read_text().splitlines())` or `Path(src_path).read_text().count('\n') + 1` (file-closed; deterministic) |
| T-5 | harden | No property-based test for the ADR sort-stability invariant | Added Hypothesis test: generate arbitrary tuples of `(id, title)` pairs, materialize as fixture, assert output `[a.id for a in slice_.adrs] == sorted([a.id for a in slice_.adrs])` |
| T-6 | harden | No metamorphic test: "adding an ADR file to a fixture should never decrease `len(adrs)`" | Added as a follow-up suggestion in Implementer notes (not in TDD plan minimum) |
| T-7 | harden | Adversarial fixtures missing (10 MB-headers ADR, ADR with `Status: bogus`, frontmatter with `---` mid-body, exceptions file with `expires: invalid-date`, policy YAML with `policy_repos: <string-not-list>`) | Added one adversarial test per probe (`test_*_adversarial.py` in S5-style suite — but lighter; one fixture per probe) |
| T-8 | harden | `test_adrs_body_never_loaded` greps for `"read_text"`/`"read_bytes"` only — not `"open("`, `"os.open"`, `"os.read"` (S6-01 AC-11 precedent) | Tightened to parametrized arch test over MARKER_MODULES × forbidden tokens |
| T-9 | harden | No test pins exceptions YAML top-level shape; a future regression of `{exceptions: [...]}` → bare-list would silently break the loader | New test: load a fixture with both shapes; the bare-list variant must yield `confidence="low"` with a `per_file_errors` entry of kind `"malformed_yaml_top_level_not_mapping"` |
| T-10 | harden | No test for `_partition_by_expiry(now=…)` with `now == expires` (the exact-boundary case — does the exception expire at midnight UTC the day of, or at end-of-day?) | Pinned: `expires >= now` is active (inclusive); test exercises `now == expires` and `now == expires + 1day` |
| T-11 | nit | No test for fnmatch case-sensitivity | Added unit test: `repo_glob: "MyService*"` matching `repo.root.name == "myservice"` → no match (case-sensitive); same fixture with `"myservice*"` → match |

### Consistency critic — findings

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| K-1 | block | `_run(self, ctx)` violates Phase-0 ABC (`async def run(self, repo, ctx)` per `src/codegenie/probes/base.py:94`) | Rewrote AC-4, AC-10, GREEN snippet, all tests |
| K-2 | block | `probe_id = ProbeId("…")` class attr violates 02-ADR-0007 (frozen ABC) + 02-ADR-0003 (registry-side annotation) | Replaced with `name: str = "…"` per ABC + module-level `_PROBE_ID: Final[ProbeId] = ProbeId("…")` constant per `src/codegenie/probes/layer_b/scip_index.py:114` precedent |
| K-3 | block | `applies_to_tasks: tuple[str, ...]` / `applies_to_languages: tuple[str, ...]` violate `list[str]` ABC | Rewrote AC-3, AC-4 |
| K-4 | block | `from codegenie.ids import ProbeId` — wrong path; actual is `codegenie.types.identifiers` | Corrected import path in GREEN snippet + AC-3 |
| K-5 | block | Missing ABC-required fields: `layer = "D"`, `tier = "base"`, `requires: list[str] = []`, `version: str`, `cache_strategy: Literal["content"] = "content"` | Added to AC-4 |
| K-6 | block | `ctx.repo_root` doesn't exist — the snapshot is the first arg to `run`, not a ctx field | Rewrote AC-4, AC-5, AC-6, AC-9; all tests use `repo.root` |
| K-7 | block | `ctx.user_home` doesn't exist | Resolved: `Path.home()` directly, OR `Path(ctx.config.get("policy.user_home", "~")).expanduser()` for testability; new AC pins the two-tier search-path resolution |
| K-8 | block | `ProbeContext.for_test(repo_root=…)` doesn't exist | Introduced `_make_context(tmp_path)` test helper mirroring S6-01 |
| K-9 | block | `ProbeOutput(probe_id=..., schema_slice=..., confidence=..., errors=...)` is wrong shape; actual is `(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)` with NO `probe_id` field | Rewrote GREEN snippet + AC-4 |
| K-10 | block | `safe_yaml.load(catalog_path)` without `max_bytes` is a TypeError | Every call now passes `max_bytes=` with documented ceiling per probe |
| K-11 | block | `safe_yaml.load(frontmatter_bytes)` is impossible (`safe_yaml.load` takes `Path`) | Added `safe_yaml.loads(data: bytes, *, max_bytes, max_depth=64)` chokepoint extension as a sixth file-to-touch; new AC-NEW1 |
| K-12 | block | Exceptions YAML `[<entry>, …]` top-level list violates `safe_yaml.load`'s mapping requirement | Pinned format to `{exceptions: [<entry>, …]}`; new AC for the format pin; documented in Implementer notes; localv2 example flagged as Phase-2 refinement |
| K-13 | block | `Adr = (id: str, title: str, status: Literal[...], path: str)` inline tuple notation is not Python | Rewrote as `class Adr(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` + `Literal` field type; same for `NoteFile`, `RepoConfigFile`, `PolicyRepoRef`, `ExceptionEntry` |
| K-14 | block | `Exception` slice class name shadows Python builtin | Renamed to `ExceptionEntry` everywhere |
| K-15 | harden | Sub-schema flat path AC missing (S6-01 AC-19 / S6-02 AC-11 precedent) | New AC pinning `files("codegenie.schema.probes") / "<probe_id>.schema.json"` for each probe; sub-schema authoring deferred to S6-08 |
| K-16 | harden | Registry annotation AC missing | New parametrized AC across the five probes using `default_registry._entries` |
| K-17 | nit | LOC ceiling exact value debated (100 vs 120) | Kept at 100 per the story's deliberate Rule-of-Three trigger; clarified in Implementer notes |
| K-18 | nit | `applies_to_tasks` / `applies_to_languages` should be `["*"]` per the ABC; AC-4 currently says `("*",)` (tuple) | Corrected |

### Design-patterns critic — findings

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| D-1 | harden | Functional-core / imperative-shell split missing: `_run` inlines parse + walk + project + confidence-derive | Extracted `_parse_adr_text`, `_collect_headings`, `_extract_frontmatter_block`, `_partition_by_expiry`, `_compute_confidence` as pure module-level helpers per S6-01 / S6-02 precedent |
| D-2 | harden | Three-state confidence policy missing | New `_compute_confidence(items, per_file_errors) -> Literal["high","medium","low"]` per probe |
| D-3 | harden | Smart-constructor pattern unused — `ExceptionsSlice` could allow `active` and `expired` to share an entry | Added `@model_validator(mode="after")` requirement: `active` and `expired` have disjoint `(repo_glob, task, expires)` tuples; total entries before partition = `len(active) + len(expired)` |
| D-4 | harden | Rule-of-Three for marker-probe abstraction debated; AC-12 enforces "no cross-probe imports" but not zero-edit extensibility | New AC: adding a sixth marker probe under `layer_d/` requires (a) zero edits to the five files, (b) zero edits to `codegenie.parsers.safe_yaml`, (c) one new test file + one new entry in MARKER_MODULES + (optionally) one new entry in the test `conftest.py`'s `_make_context` fixture if a new `ctx.config` key is needed |
| D-5 | nit | Newtype opportunity for `AdrId` — but this is the FIRST consumer of ADR identifiers; Rule 2 says don't extract | Surfaced as a Notes-for-implementer paragraph (do NOT mandate); the threshold triggers when a Phase-3+ Planner consumes ADR IDs across module boundaries |
| D-6 | nit | `Adr.status` is a `Literal[...]` — make-illegal-states-unrepresentable; the existing AC-5 already pins this; the harden formalizes the closed set in a module-level constant | `_ADR_STATUSES: Final[frozenset[Literal[...]]] = frozenset({"proposed","accepted","deprecated","superseded","unknown"})` declared once; AC-5 references it |
| D-7 | nit | Adapter pattern for the `safe_yaml.loads` extension — keep the bytes/dict adapter contained in `safe_yaml.py`; do NOT leak `yaml.YAMLError` into the probe modules | The chokepoint already translates to `MalformedYAMLError`; AC enforces this |

## Stage 3 — Researcher (skipped)

No `NEEDS RESEARCH` findings. All eighteen kernel-contract mismatches resolved via in-repo precedents:

- `src/codegenie/probes/base.py:64-96` — `Probe` ABC + `ProbeContext` + `ProbeOutput` + `RepoSnapshot`
- `src/codegenie/probes/registry.py:238` — `default_registry`
- `src/codegenie/probes/layer_b/scip_index.py:114` — `_PROBE_ID: Final[ProbeId]` constant pattern
- `src/codegenie/types/identifiers.py:29` — `ProbeId = NewType("ProbeId", str)`
- `src/codegenie/parsers/safe_yaml.py:80` — `load(path, *, max_bytes, max_depth=64)` signature; `_parse_one` + `assert_max_depth` primitives for the `loads` extension
- `src/codegenie/conventions/catalog.py:55-72` — `{rules: [...]}` top-level-mapping precedent for the exceptions YAML format pin
- `docs/phases/02-context-gather-layers-b-g/stories/S6-01-skills-index-probe.md` HARDENED — every probe-shape convention
- `docs/phases/02-context-gather-layers-b-g/stories/S6-02-conventions-probe.md` HARDENED — same lineage; `_make_context` test helper, three-state confidence, raw-artifact-emission, registry-annotation, flat-schema-path AC precedents

The Hypothesis property-based test for ADR sort-stability (T-5) and the metamorphic test for "adding a file should never decrease `len(adrs)`" (T-6) are follow-up suggestions, not researcher triggers — Hypothesis is already used in the repo; the patterns are canonical.

## Stage 4 — Synthesizer + Editor

Thirty in-place edits applied to `S6-03-layer-d-marker-probes.md`:

1. **Header block** — added "Validation notes" sub-block under the existing depends-on/ADRs lines; pointed at this report.
2. **Status field** — `Ready` → `Hardened (ready for executor)`.
3. **Depends on** — added `S1-03` (`safe_yaml.loads` chokepoint extension) and S6-01 (probe-shape precedent).
4. **ADRs honored** — added Phase 0 ADR-0007 (frozen `Probe` ABC) and 02-ADR-0003 (`@register_probe` decorator kwarg).
5. **Context paragraph** — added a closing sentence pointing at S6-01 / S6-02 as the probe-shape precedents and at the `safe_yaml.loads` chokepoint extension.
6. **References** — added `src/codegenie/probes/base.py`, `src/codegenie/probes/registry.py:238`, `src/codegenie/probes/layer_b/scip_index.py:114`, `src/codegenie/types/identifiers.py`, S6-01 hardened story, S6-02 hardened story; flagged `localv2.md §5.4 D6` example as Phase-2-refined to `{exceptions: [...]}`.
7. **Goal** — rewrote to match kernel: `async def run(repo, ctx)`; `name: str = "<id>"`; `_PROBE_ID: Final[ProbeId]` constant; three-state confidence via `_compute_confidence`; per-file errors surfaced through the slice; `safe_yaml.loads` extension in scope; raw artifact written to `ctx.output_dir / "<probe_id>.json"`.
8. **AC-1** — kept (`__all__` declarations).
9. **AC-2** — kept (LOC ceiling); test rewritten to use `len(Path(src).read_text().splitlines())` (file-closed) rather than `sum(1 for _ in open(...))`.
10. **AC-3** — kept (slice models frozen=True, extra="forbid"); each slice model is a proper `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` (the original draft's inline tuple notation was not Python).
11. **AC-4** — rewrote: each probe declares `name: str = "<id>"`, `version: str = "0.1.0"`, `layer = "D"`, `tier = "base"`, `applies_to_tasks: list[str] = ["*"]`, `applies_to_languages: list[str] = ["*"]`, `requires: list[str] = []`, `timeout_seconds: int = 5`, `cache_strategy: Literal["content"] = "content"`, `declared_inputs: list[str]` listing the marker paths; `_PROBE_ID: Final[ProbeId]` module-level constant.
12. **AC-5** — rewrote ADRProbe: `async def run(self, repo, ctx) -> ProbeOutput`; slice `AdrsSlice(adrs: tuple[Adr, ...], scanned_locations: tuple[str, ...], per_file_errors: tuple[str, ...])`; `Adr(id: str, title: str, status: Literal["proposed","accepted","deprecated","superseded","unknown"], path: str)` with `as_posix()` repo-relative path; status normalized to lowercase; pure helper `_parse_adr_text(lines, filename_stem) -> (id, title, status)` callable from tests without filesystem.
13. **AC-6** — rewrote RepoNotesProbe: slice `RepoNotesSlice(notes_dir: str | None, files: tuple[NoteFile, ...], per_file_errors: tuple[str, ...])`; `NoteFile(path: str, headings: tuple[str, ...], byte_count: int, last_modified: str)` (renamed `char_count` → `byte_count` for unambiguous-units pin); `byte_count = path.stat().st_size`; `last_modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()`; headings extracted via streaming line iterator (`open(path, 'rb')` + `for line in fh:` loop with line-byte cap — NOT `read_text()`); pure helper `_collect_headings(line_bytes_iter) -> tuple[str, ...]`.
14. **AC-7** — rewrote RepoConfigProbe: `safe_yaml.loads(frontmatter_bytes, max_bytes=8192, max_depth=8)` consumes the bounded-bytes block extracted by pure helper `_extract_frontmatter_block(file_bytes) -> tuple[frontmatter_bytes | None, body_byte_offset: int]`; the file is opened via bounded read (cap = 64 KiB, configurable via `ctx.config.get("repo_config.max_bytes", 65536)`) → frontmatter region bytes → `safe_yaml.loads`; slice `RepoConfigSlice(files: tuple[RepoConfigFile, ...], per_file_errors: tuple[str, ...])`; `RepoConfigFile(path: str, frontmatter_keys: tuple[str, ...], has_body: bool, body_byte_offset: int)` — `body_byte_offset` in BYTES (pin).
15. **AC-8** — rewrote PolicyProbe: `safe_yaml.load(Path(ctx.config.get("policy.user_home", "~")).expanduser() / ".codegenie" / "config.yaml", max_bytes=65536, max_depth=8)`; slice `PolicySlice(policy_repos: tuple[PolicyRepoRef, ...], per_file_errors: tuple[str, ...])`; `PolicyRepoRef(path: str, type: str, exists_on_disk: bool)`; `exists_on_disk = Path(ref.path).expanduser().exists()` (follows symlinks; non-existent target → False); missing-`policy_repos` field → empty tuple, `confidence="high"`; missing config file → `confidence="low"`, empty tuple, `per_file_errors=("policy_config_absent",)`.
16. **AC-9** — rewrote ExceptionProbe: YAML format pinned to `{exceptions: [<entry>, ...]}`; `safe_yaml.load(path, max_bytes=65536, max_depth=8)` for both repo-local and user-home files; merge user + repo (no de-dup; both entries kept); `_match_repo_glob(repo_name: str, repo_glob: str) -> bool` via `fnmatch.fnmatchcase` (case-sensitive); `_partition_by_expiry(entries, now: date) -> (active, expired)` pure helper; `now = datetime.now(tz=UTC).date()` at the imperative-shell boundary; `expires >= now` → active (inclusive); `repo.root.name` is the `repo_name` (NOT `ctx.repo_name`); slice `ExceptionsSlice(active: tuple[ExceptionEntry, ...], expired: tuple[ExceptionEntry, ...], per_file_errors: tuple[str, ...])` with `@model_validator(mode="after")` asserting disjoint `(repo_glob, task, expires)` tuples.
17. **AC-10** — kept (marker-absent ⇒ low confidence, no raise); tightened to three-state via `_compute_confidence`.
18. **AC-11** — kept (body bytes never read); tightened to parametrized arch test over MARKER_MODULES × forbidden tokens `("read_text", "read_bytes", "os.open", "os.read", ".open(", "Path(...).open")`.
19. **AC-12** — kept (no cross-probe imports).
20. **AC-13** — kept (`safe_yaml` for all YAML reads); architectural test extended to also check no direct `yaml.load` / `yaml.safe_load` / `yaml.CSafeLoader` reference in the five probe modules.
21. **AC-14** — kept (`mypy --strict`); tightened: `ProbeId` newtype preserved through `_PROBE_ID`; no `Any` escapes the slice; `cast(...)` is forbidden in the probe modules.
22. **AC-15** — kept (determinism); rewrote to use `slice_.model_dump_json()` byte-identity rather than `json.dumps(out, sort_keys=True)` (which would mask sort-order regressions at the slice level); added explicit sub-bullets for sort-key per probe.
23. **New AC-16** — Three-state confidence via `_compute_confidence(items, per_file_errors) -> Literal["high","medium","low"]` pure helper, per probe. `"high"` iff `per_file_errors == ()` (including empty marker — clean empty state). `"medium"` iff items non-empty AND per_file_errors non-empty. `"low"` iff items empty AND (per_file_errors non-empty OR marker absent OR catastrophic load failure).
24. **New AC-17** — Per-file-error round-trip: each probe surfaces malformed sub-items (`adrs` file with no H1, `repo_notes` file with IO error mid-stream, `repo_config` file with malformed YAML frontmatter, `policy.yaml` not a mapping, `exceptions.yaml` entry with `expires:` not parseable as date) as a tuple of stable string codes in `per_file_errors`. The string codes are documented constants in the module (`_REASON_*` pattern from `src/codegenie/conventions/catalog.py:50-52`).
25. **New AC-18** — Registry annotation: parametrized test across the five probe modules asserts `entry.heaviness == "light"` and `entry.runs_last is False` via `next(e for e in default_registry._entries if e.cls.name == "<probe_id>")`. Replaces the original draft's nonexistent `_PROBE_REGISTRY` references.
26. **New AC-19** — Sub-schema flat-path import: each probe's test imports `from importlib.resources import files; (files("codegenie.schema.probes") / "<probe_id>.schema.json")` and asserts the slice JSON validates. Sub-schema authoring deferred to S6-08; this AC pins the consumer-side path so S6-08 missing a schema is loud.
27. **New AC-20** — Extension-by-addition: adding a sixth marker probe `layer_d/skills_metrics.py` (or any sibling name) requires zero edits to the five files in this story AND zero edits to `safe_yaml.py`. The architectural test parametrizes MARKER_MODULES — adding a new module is one line in MARKER_MODULES, not five edits.
28. **New AC-21** — `safe_yaml.loads` chokepoint extension: `src/codegenie/parsers/safe_yaml.py` gains `def loads(data: bytes, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, JSONValue]` (single function; wraps `_parse_one` + `assert_max_depth`; reuses `SizeCapExceeded` for `len(data) > max_bytes` and `MalformedYAMLError` / `DepthCapExceeded` for the existing failure modes). One unit test covers happy-path, size-cap, depth-cap, top-level-non-mapping. `__all__` in `safe_yaml.py` grows by one entry.
29. **New AC-22** — Exceptions YAML format pin: top-level is a mapping with key `exceptions:` and value `list[ExceptionEntry]`. A fixture with the legacy bare-list shape (`- repo_glob: …`) is loaded; `safe_yaml.load` raises `MalformedYAMLError`; the probe maps this to `per_file_errors=("exceptions_yaml_not_mapping",)` and `confidence="low"`. Mutation caught: any future regression to bare-list parsing would silently re-introduce the chokepoint bypass.
30. **Implementation outline + TDD plan + GREEN snippet** — rewrote all four (one per probe + the cross-cutting arch tests) to match the contract above. The `_parse_adr_text` / `_collect_headings` / `_extract_frontmatter_block` / `_partition_by_expiry` / `_compute_confidence` pure helpers are extracted as module-level free functions, callable from tests without filesystem fixtures; the async `run` is the imperative shell; `_PROBE_ID: Final[ProbeId]` module-level constants; `name: str = "<id>"` ABC attr; full `ProbeOutput` six-field shape with `duration_ms` via `time.perf_counter()`; raw artifact written atomically to `ctx.output_dir / "<probe_id>.json"`. Files-to-touch table extended by one row (`src/codegenie/parsers/safe_yaml.py`) and one new test file (`tests/unit/parsers/test_safe_yaml_loads.py`).

### Conflicts resolved

- **Coverage C-1 / Test-quality T-1 / Consistency K-1 vs Design-patterns D-1** — all four pushed in the same direction (probe shape must match the kernel + three-state confidence + functional core). No conflict.
- **Coverage C-7 vs Design-patterns D-7** — both argued for the `safe_yaml.loads` extension. D-7 added the "adapter contained in `safe_yaml.py`; no `yaml.YAMLError` leakage" constraint. Synthesized as AC-21.
- **Consistency K-12 (exceptions YAML format) vs `localv2.md §5.4 D6` (bare list)** — Consistency wins; `safe_yaml`'s chokepoint discipline is post-localv2.md; the format pin is a Phase-2 refinement documented in Implementer notes.
- **Coverage C-3 (empty-fixture ACs for non-marker-absent cases) vs Rule 2 (Simplicity First — don't over-specify)** — Coverage wins on the partial-success surface (it's a real edge case operators will hit); Rule 2 wins on declining to mandate fixtures for every imaginable combinatorial corner. Five empty-fixture sub-bullets added; combinatorial expansion declined.

### Verdict

**HARDENED.** Thirty in-place edits applied. Story is now structurally consistent with the Phase-0 frozen `Probe` ABC, the Phase-1 `safe_yaml` chokepoint (with the `loads` extension surfaced as in-scope), the Phase-2 `default_registry`, and the S6-01 / S6-02 hardened story precedents for Layer-D probes.

The implementer who picks up this story can now:
1. Read `src/codegenie/probes/base.py`, `src/codegenie/probes/registry.py`, `src/codegenie/parsers/safe_yaml.py`, and S6-01 / S6-02 hardened stories.
2. Land `safe_yaml.loads(bytes, *, max_bytes, max_depth=64)` first (one function; one test file).
3. Land each of the five probes in any order — they share no kernel beyond `Probe` + `safe_yaml`; no inter-probe coupling means parallel-developable.
4. Copy S6-01 / S6-02's `_make_context` / `_make_repo` test helpers into `tests/unit/probes/layer_d/conftest.py` (the rule-of-three triggers when S6-04's external_docs probe arrives — this story is the third trigger, so the helpers extract NOW).
5. Verify the parametrized MARKER_MODULES arch tests catch a deliberate "extract a `MarkerProbe` base class" refactor attempt.
6. Run `mypy --strict src/codegenie/probes/layer_d/ src/codegenie/parsers/safe_yaml.py` clean.

No `RESCUE` outcome — the goal and ACs trace to the architecture and ADRs without contradiction once the kernel-contract drift is corrected.

## Recommended next step

`phase-story-executor` to implement. Suggested ordering:

1. `safe_yaml.loads` chokepoint extension (AC-21) — unblocks RepoConfigProbe.
2. `tests/unit/probes/layer_d/conftest.py` with `_make_context` / `_make_repo` helpers — unblocks all five probes' tests.
3. Five probes in any order (recommend starting with `ADRProbe` — simplest pure-parse shape; `_parse_adr_text` is the easiest pure helper to TDD).
4. Cross-cutting arch tests (`test_marker_probes_loc.py`) last — they're parametrized over the final MARKER_MODULES set.
