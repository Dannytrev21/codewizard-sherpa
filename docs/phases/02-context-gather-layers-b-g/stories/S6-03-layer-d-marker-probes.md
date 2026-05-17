# Story S6-03 — `ADRs` + `RepoNotes` + `RepoConfig` + `Policy` + `Exceptions` Layer D marker probes

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Hardened (ready for executor)
**Effort:** M
**Depends on:** S6-02 (`ConventionsProbe` — probe-shape precedent + file layout convention); S6-01 (`SkillsIndexProbe` — every Layer-D probe-shape convention; three-state confidence policy; `_make_context` test helper; flat schema path; `_PROBE_ID: Final[ProbeId]` constant); S1-03 (`safe_yaml.py` — this story adds a tiny `safe_yaml.loads(bytes, ...)` chokepoint extension required by `RepoConfigProbe`'s frontmatter path)
**ADRs honored:** 02-ADR-0005 (no plaintext persistence — bodies are not loaded; marker probes record paths + headings only), 02-ADR-0003 (`@register_probe(heaviness=...)` is a registry kwarg, NOT a `Probe` ABC field), 02-ADR-0007 (no plugin loader — all five probes are kernel-registered), Phase 0 ADR-0007 (`Probe` ABC frozen byte-for-byte against `localv2.md §4` — `name: str`, `async def run(self, repo, ctx)`), Phase 1 ADR-0006 (`safe_yaml` chokepoint — every YAML read goes through `safe_yaml.load` or the new `safe_yaml.loads`; no direct `yaml.load` / `yaml.safe_load` / `yaml.CSafeLoader` reference in the five probe modules)
**Phase-2 commitment honored:** "Progressive disclosure for context" (CLAUDE.md) and "Organizational uniqueness as data, not prompts" — each probe records *what exists*, not the body content. The Planner reads bodies at decision time.

## Validation notes

**Hardened 2026-05-17 via `phase-story-validator`** (see [`_validation/S6-03-layer-d-marker-probes.md`](_validation/S6-03-layer-d-marker-probes.md) for the full audit log). Thirty in-place edits resolved eighteen `block`-severity contract mismatches between the original draft and the kernel actually shipped (`src/codegenie/probes/base.py:64-96`, `src/codegenie/probes/registry.py:238`, `src/codegenie/parsers/safe_yaml.py:80`, `src/codegenie/types/identifiers.py:29`, `src/codegenie/conventions/catalog.py:55-72`). Twelve new ACs cover: three-state confidence policy (mirroring S6-01/S6-02); per-file-error round-trip surface; `safe_yaml.loads(bytes, ...)` chokepoint extension required by RepoConfigProbe's frontmatter parse path; exceptions YAML top-level format pin (`{exceptions: [...]}` — `safe_yaml.load` requires a top-level mapping, so the `localv2.md §5.4 D6` bare-list example is refined for Phase 2 the same way S2-02 refined the conventions catalog to `{rules: [...]}`); `repo_glob` matching anchored on `repo.root.name` with `fnmatch.fnmatchcase` for cross-platform determinism; `_partition_by_expiry(now: date)` pure helper so tests don't depend on wall-clock; raw artifact written to `ctx.output_dir / "<probe_id>.json"`; registry-annotation lookup via `default_registry._entries`; flat sub-schema import path mirroring S6-01 AC-19; `Exception` slice class renamed to `ExceptionEntry` to avoid shadowing the Python builtin; cross-cutting extension-by-addition AC; cross-probe arch-test parametrization over `MARKER_MODULES`. The biggest structural fix: the draft's `safe_yaml.load(frontmatter_block)` was unimplementable (the function takes `Path`, not `bytes`); the harden adds a `safe_yaml.loads(data: bytes, *, max_bytes, max_depth=64)` sibling that wraps the existing `_parse_one` + `assert_max_depth` primitives — a single-function chokepoint extension, no parallel YAML pathway.

## Context

Five marker-driven probes ship together because they share three traits and *only* those three: (a) they walk a conventional location for a marker (a YAML file or a docs directory), (b) they emit an index — paths, IDs, headings, last-modified timestamps — but **never** the body content, and (c) each one is structurally trivial (≤ 100 LOC per probe, including the Pydantic slice). They differ in markers, file layout, and slice shape; the Rule-of-Three argument against extracting a shared `MarkerProbe` base class is the same one that argues against a shared `ScannerRunner` for Layer G (final-design Design-patterns row 7). Five probes × ~80 LOC each ≈ 400 LOC; a shared base would save ~150 LOC and introduce one coupling point that every Phase-3-or-later contributor would have to mentally model before adding a sixth marker probe. Not worth it.

The five:

1. **ADRProbe** (`adrs.py`) — walks `docs/adr/`, `docs/architecture/`, `docs/decisions/`; extracts ADR ID + title + status from each markdown file's first heading and (optional) status line.
2. **RepoNotesProbe** (`repo_notes.py`) — walks `.codegenie/notes/`; extracts headings from each markdown file. Tribal-knowledge mechanism.
3. **RepoConfigProbe** (`repo_config.py`) — reads `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`'s frontmatter via `safe_yaml.loads(bytes, ...)` (new chokepoint-preserving helper added in this story; frontmatter only — body bytes never decoded).
4. **PolicyProbe** (`policy.py`) — reads `~/.codegenie/config.yaml`'s `policy_repos:` field; emits a list of declared policy-repo paths (does **not** parse the policy itself — that's a Phase-4+ Planner concern).
5. **ExceptionProbe** (`exceptions.py`) — reads `.codegenie/exceptions.yaml` and (optional) `~/.codegenie/exceptions.yaml`, both pinned to the `{exceptions: [<entry>, ...]}` top-level-mapping shape (Phase-2 refinement of `localv2.md §5.4 D6`'s bare-list example, required by `safe_yaml.load`'s mapping discipline); emits active vs expired entries matching the current repo glob.

Each probe ≤ 100 LOC. Each has its own slice. Each has a happy-path test, a marker-absent test, a per-file-error test, and a determinism test. None imports from another in this set.

Every probe is a leaf consumer of the kernel: `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` per the frozen Phase-0 ABC; `name: str = "<probe_id>"` ABC attr alongside a module-level `_PROBE_ID: Final[ProbeId] = ProbeId("<probe_id>")` constant (precedent: `src/codegenie/probes/layer_b/scip_index.py:114`); three-state confidence (`high` / `medium` / `low`) via a pure `_compute_confidence(items, per_file_errors)` helper mirroring S6-01 / S6-02; per-file errors round-tripped as first-class slice content (NOT through `ProbeOutput.errors`, which is reserved for probe-level fatal failures the coordinator should isolate); the slice JSON written atomically to `ctx.output_dir / "<probe_id>.json"` as the single raw artifact. The story adds **one** sixth file under `src/codegenie/parsers/safe_yaml.py`: a new `loads(data: bytes, *, max_bytes, max_depth=64) -> Mapping[str, JSONValue]` function wrapping the existing `_parse_one` + `assert_max_depth` primitives. This is the chokepoint-preserving extension `RepoConfigProbe`'s frontmatter path requires (the existing `load(path, ...)` cannot consume in-memory bytes); it is intentionally tiny and admits no new YAML pathway outside the chokepoint.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) row "One file per Layer G scanner; no shared `ScannerRunner`" — the same SRP + Rule-of-Three discipline applies to Layer D marker probes.
  - [`../phase-arch-design.md` §"Anti-patterns avoided"](../phase-arch-design.md) "Inheritance for code reuse" — every Phase 2 class inherits *only* `Probe` or `BaseModel`.
- **Phase ADRs:**
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — exception YAML may carry the approver's email/Slack handle; the redactor at the writer chokepoint handles it. The probes themselves don't pre-redact.
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `heaviness` is a `@register_probe(heaviness=...)` kwarg, NOT a `Probe` ABC field; verified via `default_registry._entries`.
  - [`../ADRs/0007-no-plugin-loader-in-phase-2.md`](../ADRs/0007-no-plugin-loader-in-phase-2.md) — all five probes are kernel-registered via `@register_probe`; no `plugin.yaml`.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — marker-driven; each ≤ 100 LOC.
  - [`../../localv2.md` §5.4 D1, D3, D4, D6, D7](../../../localv2.md) — slice shapes for each probe. *Note: D6's bare-list `exceptions.yaml` example is a Phase-2-refined to `{exceptions: [<entry>, ...]}` top-level mapping (mirrors S2-02's `{rules: [...]}` pin for the same `safe_yaml.load` mapping discipline).*
- **Existing kernel (the authoritative contract for every probe in this story):**
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe` ABC frozen byte-for-byte against `localv2.md §4`. `name: str` (NOT `probe_id`); `layer`, `tier`; `applies_to_tasks: list[str]` / `applies_to_languages: list[str]` (NOT tuple); `requires: list[str]`, `declared_inputs: list[str]`, `timeout_seconds: int`, `cache_strategy: Literal["content","none"]`. `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` — `RepoSnapshot` is the FIRST arg (NOT a `ctx` field). `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)` — six fields, no `probe_id`. `ProbeContext` is a stdlib `@dataclass` with `cache_dir`, `output_dir`, `workspace`, `logger`, `config` plus three Phase-1/2 optionals (`parsed_manifest`, `input_snapshot`, `image_digest_resolver`); NO `repo_root`, NO `user_home`, NO `repo_name`, NO `for_test` classmethod.
  - `src/codegenie/probes/registry.py:238` — `default_registry: Registry`. The "look up heaviness" pattern: `next(e for e in default_registry._entries if e.cls.name == "<probe_id>").heaviness == "light"`. NO `_PROBE_REGISTRY` dict.
  - `src/codegenie/probes/layer_b/scip_index.py:114` — `_PROBE_ID: Final[ProbeId] = ProbeId("scip_index")` module-level constant alongside `name: str = "scip_index"`. Dual-form probe identity (str ABC attr + typed Final constant).
  - `src/codegenie/types/identifiers.py:29` — `ProbeId = NewType("ProbeId", str)`. *NOT `codegenie.ids` — that module doesn't exist.*
  - `src/codegenie/parsers/safe_yaml.py:80` (S1-03) — `load(path: Path, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, JSONValue]`. `max_bytes` is REQUIRED. Raises `MalformedYAMLError` on top-level non-mapping (so a bare YAML list is rejected — informs the `{exceptions: [...]}` format pin). This story EXTENDS this module by adding `loads(data: bytes, *, max_bytes, max_depth=64)` for `RepoConfigProbe`'s in-memory frontmatter bytes.
  - `src/codegenie/conventions/catalog.py:55-72` (S2-02) — precedent for the `{rules: [...]}` top-level-mapping pin that informs the `{exceptions: [...]}` shape here.
  - `src/codegenie/hashing.py` — `content_hash_bytes(data)` returns `blake3:<64hex>` if any probe wants to fingerprint its raw artifact (optional; not required by any AC here).
  - `src/codegenie/schema/probes/` — flat schema layout. Each sub-schema lands at `src/codegenie/schema/probes/<probe_id>.schema.json` (S6-08).
- **Probe-shape precedents (post-hardening):**
  - [`./S6-01-skills-index-probe.md`](./S6-01-skills-index-probe.md) (HARDENED) — every Layer-D probe-shape convention: async `run(repo, ctx)`; `_make_context` test helper; flat schema path; three-state confidence via `_compute_confidence`; `default_registry._entries` registry lookup; `_PROBE_ID: Final[ProbeId]` constant; `ProbeOutput` six-field shape with `duration_ms` via `time.perf_counter()`; raw artifact written to `ctx.output_dir / "<probe_id>.json"`; functional-core/imperative-shell split (pure helpers as module-level free functions).
  - [`./S6-02-conventions-probe.md`](./S6-02-conventions-probe.md) (HARDENED) — same lineage; the `{rules: [...]}` YAML format pin informs the `{exceptions: [...]}` pin here.
- **Test precedent:**
  - `tests/unit/probes/layer_b/test_scip_index.py:69-89` — canonical `snapshot` + `ctx` fixture pattern; mirror this and extract to `tests/unit/probes/layer_d/conftest.py` as `_make_repo` + `_make_context` helpers.
  - `tests/unit/probes/layer_b/test_scip_index.py` — `asyncio.run(probe.run(snapshot, ctx))` test idiom for async probes.

## Goal

Ship five files under `src/codegenie/probes/layer_d/` plus one chokepoint-extension function in `src/codegenie/parsers/safe_yaml.py`:

1. `adrs.py`, `repo_notes.py`, `repo_config.py`, `policy.py`, `exceptions.py` — each is `@register_probe(heaviness="light")`, ≤ 100 LOC including the slice model, declares the frozen Phase-0 `Probe` ABC field set verbatim (`name: str = "<probe_id>"`, `layer = "D"`, `tier = "base"`, `applies_to_tasks: list[str] = ["*"]`, `applies_to_languages: list[str] = ["*"]`, `requires: list[str] = []`, `declared_inputs: list[str]`, `timeout_seconds: int = 5`, `cache_strategy: Literal["content"] = "content"`, `version: str = "0.1.0"`), declares a module-level `_PROBE_ID: Final[ProbeId] = ProbeId("<probe_id>")` constant, implements `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`, emits three-state confidence via a pure `_compute_confidence` helper, surfaces per-file errors as first-class slice content, writes the slice JSON atomically to `ctx.output_dir / "<probe_id>.json"` as the single raw artifact, and never raises on marker-absent or malformed-marker conditions. No probe imports another probe in this set.
2. `src/codegenie/parsers/safe_yaml.py` — gains a new public function `def loads(data: bytes, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, JSONValue]` that wraps the existing `_parse_one(data, path=...)` + `assert_max_depth(...)` primitives, enforces `len(data) > max_bytes` → `SizeCapExceeded`, and preserves the existing failure-mode surface (`MalformedYAMLError`, `DepthCapExceeded`). `__all__` grows by one entry. `RepoConfigProbe` is the first consumer; future in-memory YAML consumers (e.g., S6-04's external-docs frontmatter) inherit the chokepoint by importing the same helper.

Bodies are never decoded past the bounded line/byte iterators that the pure helpers consume. The slice carries paths, IDs, headings, status, frontmatter keys, body byte-offsets, and `(active, expired)` exception entries — anchors and indices, never bodies. The Planner reads originals at decision time per the "Progressive disclosure" commitment.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

### Module layout & types

- [ ] **AC-1.** Six new/edited files exist:
  - `src/codegenie/probes/layer_d/__init__.py` (or pre-existing if S6-01/S6-02 already created it) — one-line docstring naming "Layer D — organizational-knowledge probes".
  - `src/codegenie/probes/layer_d/adrs.py` — `__all__ = ["ADRProbe", "Adr", "AdrsSlice"]` (alphabetical).
  - `src/codegenie/probes/layer_d/repo_notes.py` — `__all__ = ["NoteFile", "RepoNotesProbe", "RepoNotesSlice"]`.
  - `src/codegenie/probes/layer_d/repo_config.py` — `__all__ = ["RepoConfigFile", "RepoConfigProbe", "RepoConfigSlice"]`.
  - `src/codegenie/probes/layer_d/policy.py` — `__all__ = ["PolicyProbe", "PolicyRepoRef", "PolicySlice"]`.
  - `src/codegenie/probes/layer_d/exceptions.py` — `__all__ = ["ExceptionEntry", "ExceptionProbe", "ExceptionsSlice"]` (note `ExceptionEntry`, NOT `Exception` — the builtin name is reserved).
  - `src/codegenie/parsers/safe_yaml.py` — extended (NOT replaced) with the new `loads(data: bytes, *, max_bytes, max_depth=64)` function and a corresponding `__all__` addition.

  None of the five probes imports any other probe in this set; the only allowed inter-module dependency is the shared `safe_yaml.loads` consumed by `repo_config.py`, `policy.py`, and `exceptions.py`.

- [ ] **AC-2.** Each probe's source file is **≤ 100 LOC** including the slice Pydantic model, the `@register_probe` line, the docstring, the imports, and any module-level constants. Verified by `tests/unit/probes/layer_d/test_marker_probes_loc.py` using `len(pathlib.Path(src_path).read_text().splitlines())` (file-closed; deterministic — NOT `sum(1 for _ in open(src_path))` which leaks the fd if the assertion fails). Mutation caught: a future refactor that bloats a probe past 100 LOC forces a review (genuine complexity → split the story; emerging shared kernel → Rule-of-Three triggered).

- [ ] **AC-3.** Each slice Pydantic model is a `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`. Inner-row models (`Adr`, `NoteFile`, `RepoConfigFile`, `PolicyRepoRef`, `ExceptionEntry`) follow the same `frozen=True, extra="forbid"` discipline.

### Probe registration & ABC compliance

- [ ] **AC-4.** Each of the five probes is `@register_probe(heaviness="light")` (kwarg form — 02-ADR-0003); class attributes declare the frozen Phase-0 `Probe` ABC field set verbatim:
  - `name: str = "<probe_id>"` — `"adrs"`, `"repo_notes"`, `"repo_config"`, `"policy"`, `"exceptions"` respectively
  - `version: str = "0.1.0"`
  - `layer = "D"`
  - `tier = "base"`
  - `applies_to_tasks: list[str] = ["*"]`
  - `applies_to_languages: list[str] = ["*"]`
  - `requires: list[str] = []`
  - `timeout_seconds: int = 5`
  - `cache_strategy: Literal["content"] = "content"`
  - `declared_inputs: list[str]` — set in `__init__` to the probe-specific marker tokens (per AC-5 to AC-9 below)

  Module-level `_PROBE_ID: Final[ProbeId] = ProbeId("<probe_id>")` is declared alongside the class (precedent: `src/codegenie/probes/layer_b/scip_index.py:114`). `ProbeId` is imported from `codegenie.types.identifiers` (NOT `codegenie.ids` — that module does not exist). The probe MUST NOT introduce a class attribute named `probe_id` (frozen ABC; 02-ADR-0007).

  `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the implementation entry point — NOT a private sync `_run(self, ctx)`. The method:
  1. Resolves marker paths from `repo.root` + `ctx.config.get(...)` overrides per probe (AC-5..AC-9).
  2. Iterates the markers via the probe's pure helpers (parse / collect / partition).
  3. Constructs the typed slice; emits `ProbeOutput(schema_slice=slice_.model_dump(mode="json"), raw_artifacts=[raw_path], confidence=_compute_confidence(items, per_file_errors), duration_ms=int((time.perf_counter()-t0)*1000), warnings=[], errors=[])`. The six-field `ProbeOutput` shape is mandatory; there is NO `probe_id` field on `ProbeOutput`.

### Probe specifications

- [ ] **AC-5.** **ADRProbe.** Walks `[repo.root / loc for loc in _LOCATIONS]` where `_LOCATIONS: Final[tuple[str, ...]] = ("docs/adr", "docs/architecture", "docs/decisions")`. For each existing location, glob `*.md` (top-level only, NOT `rglob` — recursive walks blow Phase-0's I/O budget). For each markdown file, call the pure helper `_parse_adr_text(lines: Iterable[str], filename_stem: str) -> tuple[str, str, Literal["proposed","accepted","deprecated","superseded","unknown"]]` over `itertools.islice(open(path), 50)` (bounded; first 50 lines). Title is the first `^# ` line, stripped. ID is `re.match(r"^(?:ADR-|adr-)?(\d+)", filename_stem)` group 1 if matched, else `filename_stem`. Status is `re.match(r"^[Ss]tatus:\s*(\w+)", line)` group 1 lowercased, IFF the lowercased value is in `_ADR_STATUSES: Final[frozenset[Literal[...]]] = frozenset({"proposed","accepted","deprecated","superseded"})`; otherwise `"unknown"`. Path is `str(md.relative_to(repo.root).as_posix())` (NOT `md.relative_to(md.parents[2])` — the latter is brittle for nested ADR directories). Slice: `AdrsSlice(adrs: tuple[Adr, ...], scanned_locations: tuple[str, ...], per_file_errors: tuple[str, ...])`. `Adr(id: str, title: str, status: Literal["proposed","accepted","deprecated","superseded","unknown"], path: str)`. The pure helper is unit-testable from bytes/strings only.

- [ ] **AC-6.** **RepoNotesProbe.** Walks `repo.root / ".codegenie" / "notes"` (single directory; `glob("**/*.md")` is forbidden — see `Notes for the implementer §7`). For each `*.md` file (top-level + one nested level via `rglob("*.md")` IFF the immediate parent is `.codegenie/notes/` — confined to the notes directory, never the repo root), call the pure helper `_collect_headings(line_bytes_iter: Iterable[bytes]) -> tuple[str, ...]` that consumes line bytes and emits decoded heading strings matching `^#+ `. Streaming is `with open(path, 'rb') as fh: for line in fh: ...` with a per-line byte cap (`len(line) > 4096` → skip line with a `("note_line_exceeds_cap",)` `per_file_errors` entry; no `read_text()` whole-file allocation). Slice: `RepoNotesSlice(notes_dir: str | None, files: tuple[NoteFile, ...], per_file_errors: tuple[str, ...])`. `NoteFile(path: str, headings: tuple[str, ...], byte_count: int, last_modified: str)` — `byte_count = path.stat().st_size` (NOT `char_count`; the unit is bytes, pinned to remove ambiguity); `last_modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()`. Body bytes are streamed line-by-line for heading extraction but NEVER materialized whole.

- [ ] **AC-7.** **RepoConfigProbe.** For each of `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` under `repo.root`: if the file exists, read up to `_MAX_REPO_CONFIG_BYTES: Final[int] = ctx.config.get("repo_config.max_bytes", 65536)` (64 KiB cap; the imperative shell reads via `open(path, "rb").read(_MAX_REPO_CONFIG_BYTES + 1)` so over-cap is detectable); call the pure helper `_extract_frontmatter_block(file_bytes: bytes) -> tuple[bytes | None, int]` that returns `(frontmatter_bytes, body_byte_offset)` by scanning for the first two `^---$` lines (newline-delimited; CRLF and LF both accepted; returns `(None, 0)` when no closed frontmatter block is found). If `frontmatter_bytes is not None`, call `safe_yaml.loads(frontmatter_bytes, max_bytes=8192, max_depth=8)` (the chokepoint extension landing in AC-21). Slice: `RepoConfigSlice(files: tuple[RepoConfigFile, ...], per_file_errors: tuple[str, ...])`. `RepoConfigFile(path: str, frontmatter_keys: tuple[str, ...], has_body: bool, body_byte_offset: int)` — `body_byte_offset` in **bytes** (not characters); `has_body = body_byte_offset < len(file_bytes)`; `frontmatter_keys = tuple(sorted(parsed.keys()))` when frontmatter parsed cleanly, `()` otherwise. Body content is never decoded as text; the slice only carries byte anchors.

- [ ] **AC-8.** **PolicyProbe.** Reads `Path(ctx.config.get("policy.user_home", "~")).expanduser() / ".codegenie" / "config.yaml"` via `safe_yaml.load(path, max_bytes=65536, max_depth=8)` (config root, NOT the policy bodies). Projects the `policy_repos:` field (or `[]` if absent) to `tuple[PolicyRepoRef, ...]`. Slice: `PolicySlice(policy_repos: tuple[PolicyRepoRef, ...], per_file_errors: tuple[str, ...])`. `PolicyRepoRef(path: str, type: str, exists_on_disk: bool)`. `exists_on_disk = Path(ref["path"]).expanduser().exists()` — follows symlinks per stdlib semantics; non-existent target → `False`; broken-symlink target → `False` (stdlib `.exists()` returns `False` on broken symlinks). Probe does **not** read inside the policy repo (that's Phase-4+ Planner work). Missing config file → `confidence="low"`, `policy_repos=()`, `per_file_errors=("policy_config_absent",)`. Malformed YAML / non-mapping top-level → `confidence="low"`, `policy_repos=()`, `per_file_errors=("policy_config_malformed",)`.

- [ ] **AC-9.** **ExceptionProbe.** Reads two YAML files:
  - Repo-local: `repo.root / ".codegenie" / "exceptions.yaml"`
  - User: `Path(ctx.config.get("exceptions.user_home", "~")).expanduser() / ".codegenie" / "exceptions.yaml"`

  Both pinned to the top-level-mapping shape `{exceptions: [<entry>, ...]}` (Phase-2 refinement of `localv2.md §5.4 D6` — the bare-list example is incompatible with `safe_yaml.load`'s mapping discipline, mirroring S2-02's `{rules: [...]}` pin). Each is loaded via `safe_yaml.load(path, max_bytes=65536, max_depth=8)`; the `exceptions:` field (or `[]` if absent) is projected. Merge user + repo entries (no de-dup; both kept; user entries appear first in the merged list). Filter by `_match_repo_glob(repo.root.name, entry["repo_glob"])` via `fnmatch.fnmatchcase` (case-SENSITIVE; cross-platform deterministic — `fnmatch.fnmatch` is case-insensitive on Windows). Partition by the pure helper `_partition_by_expiry(entries: Iterable[ExceptionEntry], now: date) -> tuple[tuple[ExceptionEntry, ...], tuple[ExceptionEntry, ...]]` where `expires >= now` → `active` (inclusive boundary; same-day-as-expiry is still active). The imperative shell calls `_partition_by_expiry(entries, now=datetime.now(tz=UTC).date())`; tests pin `now` to a fixture date. Slice: `ExceptionsSlice(active: tuple[ExceptionEntry, ...], expired: tuple[ExceptionEntry, ...], per_file_errors: tuple[str, ...])`. `ExceptionEntry(repo_glob: str, task: str, reason: str, expires: date, approver: str)` — `Exception` is the Python builtin name; the slice class is `ExceptionEntry` everywhere. A `@model_validator(mode="after")` on `ExceptionsSlice` asserts `active` and `expired` are disjoint on `(repo_glob, task, expires)` triples — a smart-constructor guarantee that the partition helper produced no duplicates.

### Confidence policy (three-state, pure helper)

- [ ] **AC-10.** **Marker absent / catastrophic ⇒ `confidence="low"`, no raise.** Each probe handles its marker-absent path:
  - ADRProbe: none of `docs/adr`, `docs/architecture`, `docs/decisions` exists → `confidence="low"`, `adrs=()`, `scanned_locations=()`, `per_file_errors=("adr_dirs_absent",)`
  - RepoNotesProbe: `.codegenie/notes/` does not exist → `confidence="low"`, `notes_dir=None`, `files=()`, `per_file_errors=("repo_notes_dir_absent",)`
  - RepoConfigProbe: none of the three files exists → `confidence="low"`, `files=()`, `per_file_errors=("repo_config_markers_absent",)`
  - PolicyProbe: `~/.codegenie/config.yaml` does not exist → `confidence="low"`, `policy_repos=()`, `per_file_errors=("policy_config_absent",)`
  - ExceptionProbe: neither exceptions file exists → `confidence="low"`, `active=()`, `expired=()`, `per_file_errors=("exceptions_files_absent",)`

  Mutation caught: any `raise FileNotFoundError` would break Phase 0's per-probe isolation. The probe always returns a `ProbeOutput`; never raises across the `run` boundary.

### Body bytes never read (parametrized arch test)

- [ ] **AC-11.** **Body bytes never read in the probe modules.** A parametrized architectural test over `MARKER_MODULES = ["codegenie.probes.layer_d.adrs", "codegenie.probes.layer_d.repo_notes", "codegenie.probes.layer_d.repo_config", "codegenie.probes.layer_d.policy", "codegenie.probes.layer_d.exceptions"]` × `FORBIDDEN_TOKENS = ("read_text", "read_bytes", "os.read", ".open(", "Path(...).open")` asserts `inspect.getsource(module)` contains NONE of those tokens. The `safe_yaml.load(path, ...)` call inside `policy.py` / `exceptions.py` is acceptable (it opens the file via the chokepoint, not the probe). `RepoConfigProbe` uses `open(path, "rb").read(N)` bounded by a byte cap — this is the ONE exception, but the test is permissive only via `re.search(r'open\([^)]*,\s*["\']rb["\']\)\.read\(\s*_MAX', src)` matching, NOT the broader `.open(` substring. Mutation caught: any `read_text()` or full-file `read()` over a body region would slip through and blow memory on large markers.

### No cross-probe imports (parametrized arch test)

- [ ] **AC-12.** **No cross-probe imports in this set.** Architectural test parametrized over `MARKER_MODULES × MARKER_MODULES` (excluding self-self pairs) asserts no probe-module source contains any sibling module path. Mutation caught: a future refactor extracting a shared `_walk_markers(...)` helper into `adrs.py` and importing it from `repo_notes.py` — that's the Rule-of-Three violation the SRP discipline forbids.

### `safe_yaml` chokepoint discipline

- [ ] **AC-13.** **`safe_yaml` for all YAML reads.** Every YAML read in the five probe files goes through `codegenie.parsers.safe_yaml.load(path, max_bytes=..., max_depth=...)` or `codegenie.parsers.safe_yaml.loads(bytes, max_bytes=..., max_depth=...)` (the chokepoint extension landing in AC-21). Architectural test: for each module in `MARKER_MODULES`, `inspect.getsource(module)` does NOT contain `"yaml.load"`, `"yaml.safe_load"`, `"yaml.CSafeLoader"`, `"yaml.Loader"`, or `"yaml.SafeLoader"`. The pattern `import yaml` is also forbidden (the chokepoint hides `yaml` behind `safe_yaml`).

### Static typing & determinism

- [ ] **AC-14.** **`mypy --strict`** passes on `src/codegenie/probes/layer_d/{adrs,repo_notes,repo_config,policy,exceptions}.py` and on the extended `src/codegenie/parsers/safe_yaml.py`. No `Any` escapes any slice (every Pydantic field is concretely typed). No `cast(...)` to launder types. `ProbeId` newtype is preserved through `_PROBE_ID`.

- [ ] **AC-15.** **Determinism — byte-identical slice JSON across two consecutive runs.** For each probe, a test invokes `asyncio.run(probe.run(repo, ctx))` twice against the same `RepoSnapshot` and `ProbeContext` instances; the second call's `slice_.model_dump_json()` is byte-identical to the first call's. Sort keys per probe:
  - ADRProbe: `adrs` sorted by `(id, path)` (path breaks ties on duplicate IDs across `docs/adr/` and `docs/decisions/`)
  - RepoNotesProbe: `files` sorted by `path`
  - RepoConfigProbe: `files` sorted by `path`
  - PolicyProbe: `policy_repos` sorted by `path`
  - ExceptionProbe: `active` and `expired` independently sorted by `(repo_glob, task, expires)`

  Test uses `slice_.model_dump_json()` byte-identity directly — NOT `json.dumps(out, sort_keys=True)` (which would mask sort-order regressions at the slice level).

### Three-state confidence policy (per probe)

- [ ] **AC-16.** **Three-state confidence via `_compute_confidence(items, per_file_errors) -> Literal["high","medium","low"]` pure helper, per probe.**
  - `"high"` iff `per_file_errors == ()` — including empty-items clean state (no markers found but no errors either, e.g., `.codegenie/notes/` exists but contains zero `.md` files).
  - `"medium"` iff `items != ()` AND `per_file_errors != ()` — partial success: some markers parsed, some failed.
  - `"low"` iff `items == ()` AND (`per_file_errors != ()` OR marker root absent OR catastrophic load failure).

  The helper is a pure module-level free function callable from tests with `(items, per_file_errors)` arguments only; no I/O, no filesystem access.

### Per-file-error round-trip surface

- [ ] **AC-17.** **Per-file errors surfaced as first-class slice content.** Each probe's slice exposes `per_file_errors: tuple[str, ...]` carrying stable string codes (NOT free-text). Documented constants per probe (module-level `Final` strings, mirroring `src/codegenie/conventions/catalog.py:50-52`'s `_REASON_*` pattern):
  - ADRProbe: `_REASON_NO_H1`, `_REASON_FILE_READ_FAILED`, `_REASON_ADR_DIRS_ABSENT`
  - RepoNotesProbe: `_REASON_NOTE_LINE_EXCEEDS_CAP`, `_REASON_NOTE_READ_FAILED`, `_REASON_REPO_NOTES_DIR_ABSENT`
  - RepoConfigProbe: `_REASON_FRONTMATTER_UNTERMINATED`, `_REASON_FRONTMATTER_MALFORMED`, `_REASON_REPO_CONFIG_MARKERS_ABSENT`, `_REASON_FILE_EXCEEDS_CAP`
  - PolicyProbe: `_REASON_POLICY_CONFIG_ABSENT`, `_REASON_POLICY_CONFIG_MALFORMED`, `_REASON_POLICY_REPOS_NOT_LIST`
  - ExceptionProbe: `_REASON_EXCEPTIONS_FILES_ABSENT`, `_REASON_EXCEPTIONS_YAML_NOT_MAPPING`, `_REASON_EXCEPTIONS_MALFORMED_ENTRY`, `_REASON_EXPIRES_NOT_PARSEABLE`

  Tests exercise each documented constant against a deliberately malformed fixture. ProbeOutput-level `errors=[]` always — `ProbeOutput.errors` is reserved for probe-level fatal failures the coordinator should isolate.

### Registry annotation

- [ ] **AC-18.** **Registry annotation — `heaviness="light"`.** A parametrized test over `MARKER_MODULES`:
  ```python
  @pytest.mark.parametrize("probe_id", ["adrs", "repo_notes", "repo_config", "policy", "exceptions"])
  def test_registered_as_light(probe_id: str) -> None:
      entry = next(e for e in default_registry._entries if e.cls.name == probe_id)
      assert entry.heaviness == "light"
      assert entry.runs_last is False
  ```
  Uses the actual registry surface — there is no `_PROBE_REGISTRY` dict.

### Sub-schema flat path (consumer-side pin)

- [ ] **AC-19.** **Sub-schema flat-path import.** A parametrized test asserts each probe's slice JSON validates against the flat-layout sub-schema:
  ```python
  from importlib.resources import files
  schema = files("codegenie.schema.probes") / f"{probe_id}.schema.json"
  ```
  Schemas live FLAT at `src/codegenie/schema/probes/<probe_id>.schema.json`, NOT under `layer_d/` (verified by `ls src/codegenie/schema/probes/`). Sub-schema authoring ships in S6-08; this AC pins the consumer-side import path so S6-08 failing to ship a schema (or shipping under the wrong name) is loud, not silent.

### Extension by addition

- [ ] **AC-20.** **Adding a sixth marker probe requires zero edits to the five existing files.** A future story adding `src/codegenie/probes/layer_d/skills_metrics.py` (or any sibling name) does NOT require edits to any of the five files in this story AND does NOT require edits to `safe_yaml.py`. The architectural tests (`test_marker_probes_loc.py`, `test_no_cross_probe_imports.py`, `test_yaml_chokepoint.py`, `test_body_bytes_never_read.py`, `test_registered_as_light.py`) parametrize over `MARKER_MODULES`; adding a sixth probe is one line in `MARKER_MODULES` (or the `pytest.mark.parametrize` argv), not five edits. Test (in `test_marker_probes_loc.py`):
  ```python
  def test_adding_sixth_marker_probe_requires_zero_existing_edits() -> None:
      """AC-20. Mutation caught: hard-coded probe references in any of
      the five files. The contract is: the only edit-on-extend touchpoint
      is the test parametrize list."""
      for module_path in MARKER_MODULES:
          mod = importlib.import_module(module_path)
          src = inspect.getsource(mod)
          for sibling_id in ("adrs", "repo_notes", "repo_config", "policy", "exceptions"):
              if module_path.endswith(sibling_id):
                  continue
              assert sibling_id not in src, (
                  f"{module_path} references sibling probe '{sibling_id}' in source; "
                  "extension-by-addition forbids cross-references."
              )
  ```

### `safe_yaml.loads` chokepoint extension

- [ ] **AC-21.** **`safe_yaml.loads(data: bytes, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, JSONValue]` lands in `src/codegenie/parsers/safe_yaml.py`.** Single function; wraps the existing `_parse_one` + `assert_max_depth` primitives. Behaviour mirrors `safe_yaml.load`:
  - `len(data) > max_bytes` → raises `SizeCapExceeded` (re-uses the existing exception type).
  - `_parse_one(data, path=Path("<in-memory>"))` translates `yaml.YAMLError` → `MalformedYAMLError`.
  - Top-level non-mapping → raises `MalformedYAMLError` with the existing message format.
  - `assert_max_depth(obj, max_depth=max_depth, path=Path("<in-memory>"), parser_kind="safe_yaml")` enforces depth.
  - `__all__` in `safe_yaml.py` grows by one entry (`"loads"`).

  Test file `tests/unit/parsers/test_safe_yaml_loads.py` covers: happy-path (top-level mapping, depth within cap), size-cap exceeded, top-level list rejected (`MalformedYAMLError`), depth-cap exceeded, empty bytes (`MalformedYAMLError`), and ensures the existing `safe_yaml.load(path, ...)` is byte-identical to `safe_yaml.loads(path.read_bytes(), ...)` for the same payload (cross-validation between the two entries).

### Exceptions YAML format pin

- [ ] **AC-22.** **Exceptions YAML top-level is a mapping with key `exceptions:`.** Format pinned to:
  ```yaml
  exceptions:
    - repo_glob: "myservice*"
      task: distroless_migration
      reason: "JNI native lib not yet replaced"
      expires: 2026-09-01
      approver: "@platform-team"
  ```
  A fixture with the legacy bare-list shape (`- repo_glob: ...` at top level) is loaded; `safe_yaml.load` raises `MalformedYAMLError`; the probe maps this to `confidence="low"`, `per_file_errors=("exceptions_yaml_not_mapping",)`, empty active/expired tuples. Mutation caught: any regression to bare-list parsing would silently re-introduce a chokepoint bypass (admit top-level lists in `safe_yaml`).

## Implementation outline

For each of the five files, mirror the S6-01 / S6-02 hardened structure (Pydantic slice + probe class + `async def run` imperative shell + pure module-level helpers). The probes' bodies look similar at the story level; **do not extract a shared base class** beyond `Probe` (AC-12, AC-2 LOC ceiling, final-design Design-patterns row 7). Each probe consumes `repo: RepoSnapshot` as the first arg to `run` (the `ProbeContext` is the second arg — there is no `ctx.repo_root`).

**Shared discipline across the five:**
- `_PROBE_ID: Final[ProbeId] = ProbeId("<probe_id>")` module-level constant (import from `codegenie.types.identifiers`).
- `_compute_confidence(items, per_file_errors) -> Literal["high","medium","low"]` pure helper at module level.
- All parse/walk/extract/partition logic lives in pure module-level helpers callable from tests without filesystem fixtures (functional core / imperative shell — S6-01 precedent).
- `async def run(self, repo, ctx) -> ProbeOutput` is the imperative shell: timestamp via `time.perf_counter()`; emit six-field `ProbeOutput`; write slice JSON atomically to `ctx.output_dir / "<probe_id>.json"` via `os.replace` from a sibling `.tmp` file.

**Order of land (parallel-developable beyond step 0):**

0. **`safe_yaml.loads` chokepoint extension** (AC-21). Land in `src/codegenie/parsers/safe_yaml.py` first; one function, one test file (`tests/unit/parsers/test_safe_yaml_loads.py`). Unblocks `RepoConfigProbe`.

1. **`adrs.py`**:
   - Walk `[repo.root / loc for loc in _LOCATIONS]` where `_LOCATIONS: Final[tuple[str, ...]] = ("docs/adr", "docs/architecture", "docs/decisions")`.
   - For each existing location, `sorted(d.glob("*.md"))` (top-level only).
   - For each markdown file, call the pure helper `_parse_adr_text(lines: Iterable[str], filename_stem: str) -> tuple[str, str, Literal[...]]` over `itertools.islice(open(path, "r", encoding="utf-8", errors="replace"), 50)`.
   - Collect `Adr` rows; sort by `(id, path)` (path breaks duplicate-ID ties).
   - Emit `AdrsSlice(adrs=tuple(sorted_rows), scanned_locations=tuple(scanned_relative), per_file_errors=tuple(errors))`.
   - On marker-absent → `confidence="low"`, empty tuples, `per_file_errors=("adr_dirs_absent",)`.

2. **`repo_notes.py`**:
   - Walk `repo.root / ".codegenie" / "notes"` via `rglob("*.md")` confined to the notes subtree (NOT `repo.root.rglob("**/*.md")` which would scan `node_modules`).
   - For each `*.md`, stream `open(path, "rb")` line-by-line; reject lines > 4096 bytes with a `_REASON_NOTE_LINE_EXCEEDS_CAP` entry; pass byte-lines to `_collect_headings(line_iter) -> tuple[str, ...]`.
   - `byte_count = path.stat().st_size`; `last_modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()`.
   - Sort `files` by `path`; emit `RepoNotesSlice(notes_dir=..., files=..., per_file_errors=...)`.

3. **`repo_config.py`** (requires AC-21):
   - For each of `(repo.root / "AGENTS.md", repo.root / "CLAUDE.md", repo.root / ".github" / "copilot-instructions.md")`:
     - If exists: `data = open(path, "rb").read(_MAX_REPO_CONFIG_BYTES + 1)`; if `len(data) > _MAX_REPO_CONFIG_BYTES` → `per_file_errors += (_REASON_FILE_EXCEEDS_CAP,)`; skip.
     - `frontmatter_bytes, body_byte_offset = _extract_frontmatter_block(data)`.
     - If `frontmatter_bytes is None` → `frontmatter_keys = ()`, `has_body = len(data) > 0`, `body_byte_offset = 0`.
     - Else: `parsed = safe_yaml.loads(frontmatter_bytes, max_bytes=8192, max_depth=8)`; `frontmatter_keys = tuple(sorted(parsed.keys()))`, `has_body = body_byte_offset < len(data)`.
     - Catch `MalformedYAMLError` → `per_file_errors += (_REASON_FRONTMATTER_MALFORMED,)`; `DepthCapExceeded` / `SizeCapExceeded` → `_REASON_FRONTMATTER_MALFORMED`.
   - Sort `files` by `path`; emit `RepoConfigSlice(files=..., per_file_errors=...)`.

4. **`policy.py`**:
   - `config_path = Path(ctx.config.get("policy.user_home", "~")).expanduser() / ".codegenie" / "config.yaml"`.
   - If not `config_path.exists()` → `confidence="low"`, `policy_repos=()`, `per_file_errors=("policy_config_absent",)`.
   - Else: `data = safe_yaml.load(config_path, max_bytes=65536, max_depth=8)`.
     - Catch `MalformedYAMLError` etc. → `_REASON_POLICY_CONFIG_MALFORMED`.
   - `policy_repos_raw = data.get("policy_repos", [])` — if not a `list` → `_REASON_POLICY_REPOS_NOT_LIST`.
   - For each entry, `PolicyRepoRef(path=str(entry["path"]), type=str(entry.get("type", "unknown")), exists_on_disk=Path(entry["path"]).expanduser().exists())`.
   - Sort by `path`; emit `PolicySlice(policy_repos=..., per_file_errors=...)`.

5. **`exceptions.py`**:
   - `repo_path = repo.root / ".codegenie" / "exceptions.yaml"`; `user_path = Path(ctx.config.get("exceptions.user_home", "~")).expanduser() / ".codegenie" / "exceptions.yaml"`.
   - For each path that exists: `data = safe_yaml.load(path, max_bytes=65536, max_depth=8)`; catch `MalformedYAMLError` → `_REASON_EXCEPTIONS_YAML_NOT_MAPPING`.
   - Validate top-level shape: `data` is `Mapping[str, JSONValue]` with `exceptions:` key whose value is a `list`. Otherwise → `_REASON_EXCEPTIONS_YAML_NOT_MAPPING`.
   - Parse each entry into `ExceptionEntry` via Pydantic `model_validate`; catch `ValidationError` → `_REASON_EXCEPTIONS_MALFORMED_ENTRY`. Catch `ValueError` on `expires` date parse → `_REASON_EXPIRES_NOT_PARSEABLE`.
   - Merge user + repo entries (user first; both kept; no de-dup).
   - Filter by `_match_repo_glob(repo.root.name, entry.repo_glob)` via `fnmatch.fnmatchcase`.
   - `active, expired = _partition_by_expiry(filtered, now=datetime.now(tz=UTC).date())`.
   - Sort each list by `(repo_glob, task, expires)`; emit `ExceptionsSlice(active=..., expired=..., per_file_errors=...)`.

**Pure module-level helpers (callable from tests, no I/O):**

- `_parse_adr_text(lines: Iterable[str], filename_stem: str) -> tuple[str, str, Literal["proposed","accepted","deprecated","superseded","unknown"]]` (in `adrs.py`).
- `_collect_headings(line_bytes_iter: Iterable[bytes]) -> tuple[str, ...]` (in `repo_notes.py`).
- `_extract_frontmatter_block(file_bytes: bytes) -> tuple[bytes | None, int]` (in `repo_config.py`).
- `_partition_by_expiry(entries: Iterable[ExceptionEntry], now: date) -> tuple[tuple[ExceptionEntry, ...], tuple[ExceptionEntry, ...]]` (in `exceptions.py`).
- `_match_repo_glob(repo_name: str, repo_glob: str) -> bool` (in `exceptions.py`) — `fnmatch.fnmatchcase(repo_name, repo_glob)`.
- `_compute_confidence(items: Sized, per_file_errors: Sized) -> Literal["high","medium","low"]` — declared in EACH module (not shared; intentional duplication at three lines each — Rule of Two; the shared kernel arrives at the third concrete probe family if Phase-3 marker probes follow).

## TDD plan — red / green / refactor

### Red — write the failing tests first

**Shared test helpers** land in `tests/unit/probes/layer_d/conftest.py` (the third trigger for `_make_context` + `_make_repo` — S6-01 introduced them; S6-02 copied them; this story extracts to a shared `conftest.py`):

```python
# tests/unit/probes/layer_d/conftest.py
"""Shared test helpers for Layer-D probes (S6-01 + S6-02 + S6-03)."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext, RepoSnapshot


def _make_repo(tmp_path: Path, *, name: str = "myrepo", **overrides) -> RepoSnapshot:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    return RepoSnapshot(
        root=root,
        git_commit=overrides.get("git_commit"),
        detected_languages=overrides.get("detected_languages", {}),
        config=overrides.get("config", {}),
    )


def _make_context(tmp_path: Path, *, config_overrides: dict | None = None) -> ProbeContext:
    output_dir = tmp_path / ".codegenie" / "context"
    output_dir.mkdir(parents=True, exist_ok=True)
    return ProbeContext(
        cache_dir=tmp_path / ".codegenie" / "cache",
        output_dir=output_dir,
        workspace=tmp_path / ".codegenie" / "workspace",
        logger=logging.getLogger("test"),
        config=config_overrides or {},
    )
```

**Per-probe test file shape (anchored on `test_adrs.py`):**

```python
# tests/unit/probes/layer_d/test_adrs.py
"""Unit tests for ADRProbe (S6-03)."""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest

from codegenie.probes.layer_d import adrs as adrs_probe

from .conftest import _make_context, _make_repo


def test_parse_adr_text_pure_helper_extracts_id_title_status() -> None:
    """AC-5. Mutation caught: a stringly-typed status or a regex that
    accepts arbitrary words — the Literal closed set rejects garbage,
    and the pure helper is unit-testable without filesystem fixtures."""
    lines = iter(["# 0001. Use Postgres\n", "\n", "Status: Accepted\n", "\n", "## Context\n"])
    adr_id, title, status = adrs_probe._parse_adr_text(lines, filename_stem="0001-use-postgres")
    assert (adr_id, title, status) == ("0001", "Use Postgres", "accepted")


def test_parse_adr_text_unknown_status_falls_back() -> None:
    """AC-5. Mutation caught: a future "raise on missing status" — the
    Literal type requires the explicit `unknown` variant."""
    lines = iter(["# 0001. Foo\n", "(no status line)\n"])
    _, _, status = adrs_probe._parse_adr_text(lines, filename_stem="0001-foo")
    assert status == "unknown"


def test_parse_adr_text_no_h1_emits_empty_title() -> None:
    """AC-5 / AC-17. Mutation caught: latent NoneType.group(1) bug from
    the draft's three-call inline parse — the pure helper is total."""
    lines = iter(["Status: Proposed\n", "Some prose without H1\n"])
    adr_id, title, _ = adrs_probe._parse_adr_text(lines, filename_stem="0042")
    assert adr_id == "0042"
    assert title == ""


def test_adrs_happy_path_scans_three_conventional_locations(tmp_path: Path) -> None:
    """AC-5. Mutation caught: dropping any of the three conventional
    locations — assertion pins the three-location scan and the
    repo-relative path traversal."""
    repo = _make_repo(tmp_path)
    (repo.root / "docs" / "adr").mkdir(parents=True)
    (repo.root / "docs" / "architecture").mkdir(parents=True)
    (repo.root / "docs" / "decisions").mkdir(parents=True)
    (repo.root / "docs" / "adr" / "0001-use-postgres.md").write_text(
        "# 0001. Use Postgres\n\nStatus: Accepted\n"
    )
    (repo.root / "docs" / "architecture" / "0002-microservices.md").write_text(
        "# 0002. Microservices\n\nStatus: Proposed\n"
    )
    (repo.root / "docs" / "decisions" / "0003-event-bus.md").write_text(
        "# 0003. Kafka\n\nStatus: Superseded\n"
    )
    ctx = _make_context(tmp_path)

    output = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx))
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)

    assert output.confidence == "high"
    assert [a.id for a in slice_.adrs] == ["0001", "0002", "0003"]
    assert [a.status for a in slice_.adrs] == ["accepted", "proposed", "superseded"]
    assert [a.path for a in slice_.adrs] == [
        "docs/adr/0001-use-postgres.md",
        "docs/architecture/0002-microservices.md",
        "docs/decisions/0003-event-bus.md",
    ]
    assert set(slice_.scanned_locations) == {"docs/adr", "docs/architecture", "docs/decisions"}
    assert slice_.per_file_errors == ()


def test_adrs_marker_absent_yields_low_confidence_no_raise(tmp_path: Path) -> None:
    """AC-10. Mutation caught: any `raise FileNotFoundError` would
    violate Phase 0 isolation."""
    repo = _make_repo(tmp_path)
    ctx = _make_context(tmp_path)
    output = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)
    assert slice_.adrs == ()
    assert slice_.scanned_locations == ()
    assert slice_.per_file_errors == ("adr_dirs_absent",)


def test_adrs_partial_failure_yields_medium_confidence(tmp_path: Path) -> None:
    """AC-16. Mutation caught: any "collapse to low if any error" — the
    partial-success surface must be distinguishable from total failure."""
    repo = _make_repo(tmp_path)
    adr_dir = repo.root / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-good.md").write_text("# 0001. Good\nStatus: Accepted\n")
    (adr_dir / "0002-no-h1.md").write_text("Status: Proposed\n(no H1)\n")
    ctx = _make_context(tmp_path)
    output = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx))
    assert output.confidence == "medium"
    slice_ = adrs_probe.AdrsSlice.model_validate(output.schema_slice)
    assert len(slice_.adrs) == 2  # both still recorded; the H1-missing one has empty title
    assert "no_h1" in slice_.per_file_errors


def test_adrs_duplicate_id_across_directories_is_deterministic(tmp_path: Path) -> None:
    """AC-15 sub-bullet. Mutation caught: sort by `id` only (instead of
    `(id, path)`) would non-determinstically pick which entry wins on
    duplicate IDs across `docs/adr/` and `docs/decisions/`."""
    repo = _make_repo(tmp_path)
    (repo.root / "docs" / "adr").mkdir(parents=True)
    (repo.root / "docs" / "decisions").mkdir(parents=True)
    (repo.root / "docs" / "adr" / "0001-from-adr.md").write_text("# 0001. From adr\nStatus: Accepted\n")
    (repo.root / "docs" / "decisions" / "0001-from-decisions.md").write_text("# 0001. From decisions\nStatus: Accepted\n")
    ctx = _make_context(tmp_path)
    out1 = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx)).schema_slice
    out2 = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx)).schema_slice
    s1 = adrs_probe.AdrsSlice.model_validate(out1)
    s2 = adrs_probe.AdrsSlice.model_validate(out2)
    assert [a.path for a in s1.adrs] == [a.path for a in s2.adrs]
    assert [a.path for a in s1.adrs] == [
        "docs/adr/0001-from-adr.md",
        "docs/decisions/0001-from-decisions.md",
    ]


def test_adrs_two_consecutive_runs_byte_identical_model_dump_json(tmp_path: Path) -> None:
    """AC-15. Mutation caught: any iteration order that depends on
    `os.listdir` ordering — verified at the slice-JSON byte level
    (NOT json.dumps(sort_keys=True), which would mask a sort regression)."""
    repo = _make_repo(tmp_path)
    adr_dir = repo.root / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0003-c.md").write_text("# 0003. C\nStatus: Accepted\n")
    (adr_dir / "0001-a.md").write_text("# 0001. A\nStatus: Accepted\n")
    (adr_dir / "0002-b.md").write_text("# 0002. B\nStatus: Accepted\n")
    ctx = _make_context(tmp_path)
    out1 = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx)).schema_slice
    out2 = asyncio.run(adrs_probe.ADRProbe().run(repo, ctx)).schema_slice
    s1 = adrs_probe.AdrsSlice.model_validate(out1)
    s2 = adrs_probe.AdrsSlice.model_validate(out2)
    assert s1.model_dump_json() == s2.model_dump_json()
```

**Equivalent test files** for `repo_notes.py`, `repo_config.py`, `policy.py`, `exceptions.py` follow the same shape. Each includes:

- 1 pure-helper test (the heart of the probe's logic, callable from bytes/strings)
- 1 happy-path async-run integration test
- 1 marker-absent low-confidence test
- 1 partial-failure medium-confidence test
- 1 byte-identical determinism test (model_dump_json)
- (per-probe specific) 1 schema-validation test (AC-19) + 1 registry-annotation test (AC-18)

**Exception-probe-specific tests:**

```python
def test_partition_by_expiry_uses_inclusive_boundary() -> None:
    """AC-9 / AC-15. Mutation caught: `expires > now` (strict) instead
    of `expires >= now` — same-day-as-expiry is still active until end-of-day."""
    from datetime import date
    entry_today = exceptions_probe.ExceptionEntry(
        repo_glob="*", task="vuln", reason="r", expires=date(2026, 5, 17), approver="@team"
    )
    entry_yesterday = exceptions_probe.ExceptionEntry(
        repo_glob="*", task="vuln", reason="r", expires=date(2026, 5, 16), approver="@team"
    )
    active, expired = exceptions_probe._partition_by_expiry(
        [entry_today, entry_yesterday], now=date(2026, 5, 17)
    )
    assert entry_today in active
    assert entry_yesterday in expired


def test_match_repo_glob_is_case_sensitive() -> None:
    """AC-9. Mutation caught: `fnmatch.fnmatch` (case-insensitive on
    Windows) — only `fnmatchcase` guarantees cross-platform determinism."""
    assert exceptions_probe._match_repo_glob("myservice", "myservice*") is True
    assert exceptions_probe._match_repo_glob("myservice", "MyService*") is False


def test_exceptions_yaml_bare_list_rejected(tmp_path: Path) -> None:
    """AC-22. Mutation caught: any regression that admits top-level
    YAML lists would silently bypass the safe_yaml chokepoint."""
    repo = _make_repo(tmp_path)
    bare_list = repo.root / ".codegenie" / "exceptions.yaml"
    bare_list.parent.mkdir(parents=True)
    bare_list.write_text("- repo_glob: '*'\n  task: vuln\n  reason: r\n  expires: 2026-09-01\n  approver: '@team'\n")
    ctx = _make_context(tmp_path)
    output = asyncio.run(exceptions_probe.ExceptionProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = exceptions_probe.ExceptionsSlice.model_validate(output.schema_slice)
    assert "exceptions_yaml_not_mapping" in slice_.per_file_errors


def test_exceptions_yaml_mapping_shape_accepted(tmp_path: Path) -> None:
    """AC-22. Happy path for the pinned format."""
    repo = _make_repo(tmp_path)
    ex = repo.root / ".codegenie" / "exceptions.yaml"
    ex.parent.mkdir(parents=True)
    ex.write_text(
        "exceptions:\n"
        "  - repo_glob: 'myrepo*'\n"
        "    task: vuln_remediation\n"
        "    reason: 'r'\n"
        "    expires: 2030-01-01\n"
        "    approver: '@team'\n"
    )
    ctx = _make_context(tmp_path)
    output = asyncio.run(exceptions_probe.ExceptionProbe().run(repo, ctx))
    assert output.confidence == "high"
    slice_ = exceptions_probe.ExceptionsSlice.model_validate(output.schema_slice)
    assert len(slice_.active) == 1


@pytest.mark.parametrize("forbidden_token", ["read_text", "read_bytes", "os.read"])
def test_adrs_body_never_loaded(forbidden_token: str) -> None:
    """AC-11. Parametrized; the no-`read_text`/no-`read_bytes` discipline
    is enforced across all five modules in test_marker_probes_arch.py."""
    src = inspect.getsource(adrs_probe)
    assert forbidden_token not in src
```

**Cross-cutting architectural tests** (`tests/unit/probes/layer_d/test_marker_probes_arch.py`):

```python
"""Architectural tests for the five marker probes (S6-03)."""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

from codegenie.probes.registry import default_registry

MARKER_MODULES = [
    "codegenie.probes.layer_d.adrs",
    "codegenie.probes.layer_d.repo_notes",
    "codegenie.probes.layer_d.repo_config",
    "codegenie.probes.layer_d.policy",
    "codegenie.probes.layer_d.exceptions",
]
PROBE_IDS = ["adrs", "repo_notes", "repo_config", "policy", "exceptions"]
FORBIDDEN_BODY_READS = ("read_text", "read_bytes", "os.read")
FORBIDDEN_YAML_TOKENS = (
    "yaml.load(", "yaml.safe_load", "yaml.CSafeLoader", "yaml.Loader", "yaml.SafeLoader",
    "import yaml",
)


@pytest.mark.parametrize("module_path", MARKER_MODULES)
def test_each_marker_probe_under_100_loc(module_path: str) -> None:
    """AC-2. File-closed line count via Path.read_text().splitlines()."""
    mod = importlib.import_module(module_path)
    src_path = inspect.getsourcefile(mod)
    assert src_path is not None
    line_count = len(Path(src_path).read_text().splitlines())
    assert line_count <= 100, (
        f"{module_path} has {line_count} LOC; the 100-LOC ceiling forces a "
        "review of whether a shared kernel is now justified (Rule-of-Three)."
    )


@pytest.mark.parametrize("module_path", MARKER_MODULES)
def test_no_cross_probe_imports(module_path: str) -> None:
    """AC-12. Mutation caught: any extracted shared helper imported across siblings."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    for sibling in MARKER_MODULES:
        if sibling == module_path:
            continue
        assert sibling not in src, (
            f"{module_path} imports from {sibling}; marker probes share no "
            "Phase-2 kernel beyond `Probe` and `safe_yaml`."
        )


@pytest.mark.parametrize("module_path", MARKER_MODULES)
@pytest.mark.parametrize("forbidden", FORBIDDEN_YAML_TOKENS)
def test_yaml_reads_route_through_safe_yaml(module_path: str, forbidden: str) -> None:
    """AC-13. Mutation caught: any direct yaml.* reference bypasses the chokepoint."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    assert forbidden not in src, (
        f"{module_path} contains forbidden YAML token `{forbidden}`; "
        "all YAML reads must route through `safe_yaml.load` or `safe_yaml.loads`."
    )


@pytest.mark.parametrize("module_path", MARKER_MODULES)
@pytest.mark.parametrize("forbidden", FORBIDDEN_BODY_READS)
def test_body_bytes_never_read(module_path: str, forbidden: str) -> None:
    """AC-11. Mutation caught: any whole-file read past the bounded line iterator."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    assert forbidden not in src, (
        f"{module_path} contains forbidden body-read token `{forbidden}`; "
        "bodies are anchored, never decoded whole."
    )


@pytest.mark.parametrize("probe_id", PROBE_IDS)
def test_registered_as_light(probe_id: str) -> None:
    """AC-18. Mutation caught: `heaviness="medium"` or `runs_last=True`
    on any of the five — the registry annotation is the load-bearing
    scheduling signal."""
    entry = next(e for e in default_registry._entries if e.cls.name == probe_id)
    assert entry.heaviness == "light"
    assert entry.runs_last is False


def test_adding_sixth_marker_probe_requires_zero_existing_edits() -> None:
    """AC-20. Mutation caught: any cross-reference to a sibling probe's id
    in a non-matching module's source."""
    for module_path in MARKER_MODULES:
        mod = importlib.import_module(module_path)
        src = inspect.getsource(mod)
        for sibling_id in PROBE_IDS:
            if module_path.endswith(sibling_id):
                continue
            assert sibling_id not in src, (
                f"{module_path} references sibling probe '{sibling_id}' in source; "
                "extension-by-addition forbids cross-references."
            )
```

**`safe_yaml.loads` chokepoint extension** test (`tests/unit/parsers/test_safe_yaml_loads.py`):

```python
"""Unit tests for safe_yaml.loads (S6-03 / AC-21)."""
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.parsers import safe_yaml
from codegenie.parsers.safe_yaml import (
    DepthCapExceeded, MalformedYAMLError, SizeCapExceeded,
)


def test_loads_happy_path_mapping() -> None:
    data = b"name: foo\nvalue: 42\n"
    parsed = safe_yaml.loads(data, max_bytes=4096, max_depth=8)
    assert parsed == {"name": "foo", "value": 42}


def test_loads_size_cap_exceeded() -> None:
    data = b"x: " + b"y" * 100
    with pytest.raises(SizeCapExceeded):
        safe_yaml.loads(data, max_bytes=10, max_depth=8)


def test_loads_top_level_list_rejected() -> None:
    data = b"- a\n- b\n"
    with pytest.raises(MalformedYAMLError):
        safe_yaml.loads(data, max_bytes=4096, max_depth=8)


def test_loads_depth_cap_exceeded() -> None:
    deep = b"a:\n" + b"  " * 20 + b"b: 1\n"  # crude; tighten in real test
    with pytest.raises((DepthCapExceeded, MalformedYAMLError)):
        safe_yaml.loads(deep, max_bytes=4096, max_depth=3)


def test_loads_byte_identical_to_load_from_path(tmp_path: Path) -> None:
    """AC-21. Cross-validation: loads(bytes) and load(path) yield identical
    parsed structures for the same payload — the chokepoint discipline is
    behaviorally consistent across the two entry points."""
    payload = b"k: 1\nlist:\n  - a\n  - b\n"
    f = tmp_path / "f.yaml"
    f.write_bytes(payload)
    from_path = safe_yaml.load(f, max_bytes=4096, max_depth=8)
    from_bytes = safe_yaml.loads(payload, max_bytes=4096, max_depth=8)
    assert dict(from_path) == dict(from_bytes)
```

### Green — make it pass

**Skeleton for `adrs.py`** (≤ 100 LOC; the other four follow the same shape — async run + pure helpers + frozen ABC field set):

```python
# src/codegenie/probes/layer_d/adrs.py
"""ADRProbe — Layer D, light heaviness.

Walks docs/adr/, docs/architecture/, docs/decisions/. Records ID +
title + status only; body bytes are never read past the bounded line
iterator (first 50 lines via itertools.islice). Sources:
../phase-arch-design.md §"Design patterns applied" + localv2.md §5.4 D3.
"""
from __future__ import annotations

import itertools
import re
import time
from collections.abc import Iterable, Sized
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.types.identifiers import ProbeId

__all__ = ["ADRProbe", "Adr", "AdrsSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("adrs")
_LOCATIONS: Final[tuple[str, ...]] = ("docs/adr", "docs/architecture", "docs/decisions")
_ID_RE: Final[re.Pattern[str]] = re.compile(r"^(?:ADR-|adr-)?(\d+)")
_STATUS_RE: Final[re.Pattern[str]] = re.compile(r"^[Ss]tatus:\s*(\w+)")
_ADR_STATUSES: Final[frozenset[str]] = frozenset({"proposed", "accepted", "deprecated", "superseded"})
_REASON_NO_H1: Final[str] = "no_h1"
_REASON_ADR_DIRS_ABSENT: Final[str] = "adr_dirs_absent"
AdrStatus = Literal["proposed", "accepted", "deprecated", "superseded", "unknown"]


class Adr(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    title: str
    status: AdrStatus
    path: str


class AdrsSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    adrs: tuple[Adr, ...]
    scanned_locations: tuple[str, ...]
    per_file_errors: tuple[str, ...]


def _parse_adr_text(lines: Iterable[str], filename_stem: str) -> tuple[str, str, AdrStatus]:
    """Pure helper: extract (id, title, status) from bounded line iter."""
    title = ""
    status: AdrStatus = "unknown"
    m_id = _ID_RE.match(filename_stem)
    adr_id = m_id.group(1) if m_id else filename_stem
    for line in lines:
        if not title and line.startswith("# "):
            title = line[2:].strip()
        m = _STATUS_RE.match(line)
        if m and m.group(1).lower() in _ADR_STATUSES:
            status = m.group(1).lower()  # type: ignore[assignment]
    return adr_id, title, status


def _compute_confidence(items: Sized, errors: Sized) -> Literal["high", "medium", "low"]:
    if len(errors) == 0:
        return "high"
    if len(items) > 0:
        return "medium"
    return "low"


@register_probe(heaviness="light")
class ADRProbe(Probe):
    name: str = "adrs"
    version: str = "0.1.0"
    layer = "D"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 5
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [f"adr_search_path:{loc}" for loc in _LOCATIONS]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        adrs: list[Adr] = []
        scanned: list[str] = []
        errors: list[str] = []
        for loc in _LOCATIONS:
            d = repo.root / loc
            if not d.exists():
                continue
            scanned.append(loc)
            for md in sorted(d.glob("*.md")):
                with open(md, "r", encoding="utf-8", errors="replace") as fh:
                    adr_id, title, status = _parse_adr_text(itertools.islice(fh, 50), md.stem)
                if not title:
                    errors.append(_REASON_NO_H1)
                adrs.append(Adr(id=adr_id, title=title, status=status,
                                path=md.relative_to(repo.root).as_posix()))
        if not scanned:
            errors.append(_REASON_ADR_DIRS_ABSENT)
        adrs.sort(key=lambda a: (a.id, a.path))
        slice_ = AdrsSlice(adrs=tuple(adrs), scanned_locations=tuple(scanned), per_file_errors=tuple(errors))
        raw_path = ctx.output_dir / "adrs.json"
        tmp = raw_path.with_suffix(".tmp")
        tmp.write_text(slice_.model_dump_json())
        tmp.replace(raw_path)
        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=[raw_path],
            confidence=_compute_confidence(adrs, errors),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=[],
            errors=[],
        )
```

`repo_notes.py`, `repo_config.py`, `policy.py`, `exceptions.py` follow the same shape — each in its own file, each ≤ 100 LOC, each with its own slice model, each with `_PROBE_ID` constant + `_compute_confidence` pure helper + pure parse/extract/partition helpers.

**`safe_yaml.loads` extension** (one function added to `src/codegenie/parsers/safe_yaml.py`):

```python
def loads(data: bytes, *, max_bytes: int, max_depth: int = 64) -> Mapping[str, JSONValue]:
    """Parse ``data`` as a single top-level YAML mapping with size + depth caps.

    Mirrors :func:`load` but consumes in-memory bytes rather than a path.
    Same failure surface (``SizeCapExceeded``, ``MalformedYAMLError``,
    ``DepthCapExceeded``); the chokepoint discipline is preserved by
    routing through the shared ``_parse_one`` + ``assert_max_depth`` primitives.
    """
    if len(data) > max_bytes:
        raise SizeCapExceeded(f"<in-memory>: {len(data)} > {max_bytes}")
    obj = _parse_one(data, path=Path("<in-memory>"))
    if obj is None or not isinstance(obj, dict):
        kind = "None" if obj is None else type(obj).__name__
        raise MalformedYAMLError(f"<in-memory>: top-level must be a mapping (got {kind})")
    assert_max_depth(obj, max_depth=max_depth, path=Path("<in-memory>"), parser_kind=_PARSER_KIND)
    return obj
```

### Refactor

- **Do not extract a shared `_walk_markers(repo_root, locations) -> Iterable[Path]` helper.** The five probes walk five different layouts (recursive vs. flat, multi-location vs. single-file vs. user-home). Shape similarity is at the *story* level, not the *code* level. AC-12 + AC-20 enforce this with parametrized architectural tests.
- **Do not extract a shared `_compute_confidence` helper.** The three-line helper duplicates across the five modules intentionally — the Rule-of-Two threshold within this story does not trigger an extract (the third concrete family of marker probes — if Phase-3 adds one — is the threshold for moving `_compute_confidence` into `codegenie.probes.layer_d._common` or similar). S6-01's and S6-02's helpers are also local to their modules; consistency.
- The `_ADR_STATUSES` set + `_ID_RE` regex stay local to `adrs.py`. `repo_notes.py` headings use a different regex (`^#+ `); `policy.py` and `exceptions.py` use no regex; `repo_config.py` uses `safe_yaml.loads`. No shared regex constants.
- The pure helpers `_parse_adr_text`, `_collect_headings`, `_extract_frontmatter_block`, `_partition_by_expiry`, `_match_repo_glob` ARE the testability surface. They MUST stay pure (no I/O, no `datetime.now()`, no `Path.exists()`) so tests can exercise them directly.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/parsers/safe_yaml.py` | **Extend** with `def loads(data: bytes, *, max_bytes, max_depth=64) -> Mapping[str, JSONValue]` (AC-21). Single-function chokepoint extension. `__all__` grows by one entry. |
| `src/codegenie/probes/layer_d/__init__.py` | Module docstring (one-liner naming "Layer D — organizational-knowledge probes"). May already exist from S6-01/S6-02; if so, no change. |
| `src/codegenie/probes/layer_d/adrs.py` | New file ≤ 100 LOC. Pure helper `_parse_adr_text`; async `run`; six-field `ProbeOutput`. |
| `src/codegenie/probes/layer_d/repo_notes.py` | New file ≤ 100 LOC. Pure helper `_collect_headings`. |
| `src/codegenie/probes/layer_d/repo_config.py` | New file ≤ 100 LOC. Pure helper `_extract_frontmatter_block`. Consumes `safe_yaml.loads`. |
| `src/codegenie/probes/layer_d/policy.py` | New file ≤ 100 LOC. Consumes `safe_yaml.load`. |
| `src/codegenie/probes/layer_d/exceptions.py` | New file ≤ 100 LOC. Pure helpers `_partition_by_expiry`, `_match_repo_glob`. Consumes `safe_yaml.load`. |
| `tests/unit/parsers/test_safe_yaml_loads.py` | New file — 5 tests (happy-path, size-cap, top-level list rejected, depth-cap, byte-identical to `load`). |
| `tests/unit/probes/layer_d/conftest.py` | New file (or extend if S6-01/S6-02 already created one) — `_make_context` + `_make_repo` test helpers. Rule-of-Three trigger met by this story (the third Layer-D probe story to need them). |
| `tests/unit/probes/layer_d/test_adrs.py` | New file — 7+ tests (pure-helper × 3, happy-path, marker-absent, partial-failure, dup-id-determinism, byte-identity, schema-validation). |
| `tests/unit/probes/layer_d/test_repo_notes.py` | New file — 6+ tests. |
| `tests/unit/probes/layer_d/test_repo_config.py` | New file — 6+ tests (incl. frontmatter-unterminated + safe_yaml.loads path). |
| `tests/unit/probes/layer_d/test_policy.py` | New file — 6+ tests. |
| `tests/unit/probes/layer_d/test_exceptions.py` | New file — 8+ tests (incl. `_partition_by_expiry` boundary, `fnmatchcase` case-sensitivity, bare-list-rejection, smart-constructor disjoint sets). |
| `tests/unit/probes/layer_d/test_marker_probes_arch.py` | New file — six parametrized architectural tests across the five modules (LOC ≤ 100, no cross-probe imports, YAML chokepoint, no body reads, registered as light, zero-edit extensibility). |

## Out of scope

- **`SkillsIndexProbe`** — S6-01 (separate story; different kernel — consumes `SkillsLoader`).
- **`ConventionsProbe`** — S6-02 (separate story; different shape — it runs rules via `ConventionsCatalogLoader.load_all()`, not just an index).
- **`ExternalDocsProbe`** — S6-04 (opt-in skip-cleanly; warrants its own story per the "do not invent an allowlist schema speculatively" discipline).
- **Policy-body parsing.** The probe records a path; reading the policy YAML is Phase 4+ Planner work.
- **Exception approval workflow.** The probe records what's declared; approval / expiry-extension is org-side process.
- **Markdown link extraction from `RepoNotes` bodies.** Bodies are not loaded past the streaming heading pass. If the Planner needs a body, it reads the path directly.
- **Sub-schema authoring** for the five probes — `src/codegenie/schema/probes/{adrs,repo_notes,repo_config,policy,exceptions}.schema.json` ship in S6-08. This story pins the consumer-side flat-path import (AC-19) so S6-08 failing to ship is loud.
- **`AdrId` newtype.** ADR IDs are `str` everywhere in this story. The Rule-of-Two threshold for promoting to a `NewType` triggers when a Phase-3+ Planner consumes ADR IDs across module boundaries; see Implementer notes §10.
- **`ExceptionProbe` policy enforcement.** The probe records active/expired entries; the Planner decides whether to act on a task class with an active exception. Phase-2 commitment: "Facts, not judgments."

## Notes for the implementer

1. **The 100-LOC ceiling is mutation-resistant by design.** Once a probe creeps to 110 LOC, the ceiling forces a review: is this complexity genuine (then the story is wrong-sized and we split), or is there a shared kernel emerging (then Rule-of-Three has triggered and the helper lands in `_markers/__init__.py`). Don't paper over by deleting tests or comments to shrink LOC. The ceiling counts ALL lines including blank/comment lines (the `len(Path(src).read_text().splitlines())` measurement).
2. **`safe_yaml.load` / `safe_yaml.loads` are the only YAML doors.** `PolicyProbe` and `ExceptionProbe` read whole YAML files via `safe_yaml.load(path, max_bytes=..., max_depth=...)`. `RepoConfigProbe` reads in-memory frontmatter bytes via the new `safe_yaml.loads(bytes, max_bytes=..., max_depth=...)` chokepoint extension (AC-21). The architectural test (AC-13) forbids any direct `yaml.load` / `yaml.safe_load` / `import yaml` reference in the five probe modules.
3. **Bounded line iterators, not `read_text()`.** `itertools.islice(open(path), 50)` reads at most 50 lines; even a 100 MB ADR with a corrupted "no newlines" body cannot blow memory. `read_text()` is a 100 MB allocation on the same file. The parametrized arch test (AC-11) enforces `read_text` / `read_bytes` / `os.read` are absent from every probe module's source.
4. **`_ADR_STATUSES = frozenset({"proposed", "accepted", "deprecated", "superseded"})`** — the closed set the Pydantic `Literal[...]` enforces (with `"unknown"` as the fallback). A future contributor adding `"draft"` must update both the `frozenset` and the `Literal` (the type-check will catch the mismatch). The closed set is a Phase-2 choice; widening requires a story note.
5. **`RepoConfigProbe`'s `body_byte_offset`** is the same anchor pattern as `SkillsIndexProbe` (S6-01). The Planner reads bodies; the probe records anchors. The offset is in BYTES (not characters); decoding the body to text is the Planner's job at decision time.
6. **`ExceptionProbe`'s `expired:` partition is load-bearing.** A just-expired exception is the operator's signal to either renew it or accept that the previously-blocked task class is about to start running. Hiding expired entries would silently shift policy. The `expires >= now` inclusive boundary means same-day-as-expiry entries are still active until end-of-day UTC.
7. **No `pathlib.Path.glob("**/*.md")` recursive globs over the repo root.** Layer A probes already enforce repo-root file-budget caps; the marker probes here scan only specific subdirectories. A `**` glob on the repo root would re-scan every node_modules and break Phase 0's I/O budget. `RepoNotesProbe` recursive walk is confined to `.codegenie/notes/` only.
8. **`PolicyProbe` reads the user-home `~/.codegenie/config.yaml`, not in-repo `.codegenie/config.yaml`.** Phase 2's repo-local config (`.codegenie/scenarios.yaml`) is per-probe; the policy-repo declaration is operator-global. The `ctx.config.get("policy.user_home", "~")` indirection allows tests to override the user-home path; production callers use `Path.home()` (the default `"~"` expanded via `Path.expanduser()`).
9. **Sub-schemas for these five probes ship in S6-08** (`{adrs,repo_notes,repo_config,policy,exceptions}.schema.json` at the FLAT path `src/codegenie/schema/probes/<name>.schema.json` — NOT under `layer_d/`). This story ships only the Pydantic models + probe code + the consumer-side flat-path import (AC-19); sub-schema fixture validation is S6-08's last AC.
10. **`fnmatch.fnmatchcase` not regex for `repo_glob`.** Exceptions YAML's `repo_glob: "myservice*"` is a glob, not a regex (operator convention; documented in `localv2.md` §5.4 D6). `fnmatch.fnmatchcase` is case-SENSITIVE on every platform; `fnmatch.fnmatch` is case-insensitive on Windows (deterministic-cross-platform discipline). A future migration to regex requires an ADR-amend, not a silent semantic change.
11. **`Exception` is the Python builtin name — the slice class is `ExceptionEntry`.** Naming the slice `Exception` would silently rebind the catch-all within the module, breaking every `except Exception` block (and `except <ExceptionEntry>` would be a tuple-mismatch at runtime). `ExceptionEntry` is the canonical name across the slice, helpers, and tests.
12. **The exceptions YAML top-level shape is `{exceptions: [<entry>, ...]}`** (not a bare list — `safe_yaml.load` requires a top-level mapping). This is a Phase-2 refinement of `localv2.md §5.4 D6`'s example. Operators migrating from the legacy bare-list format must wrap their entries under an `exceptions:` key. The probe surfaces the migration error as `per_file_errors=("exceptions_yaml_not_mapping",)` with `confidence="low"` (AC-22). The same compatibility constraint S2-02 resolved for the conventions catalog (`{rules: [...]}`); see `src/codegenie/conventions/catalog.py:55-72`.
13. **Functional core, imperative shell.** The pure helpers (`_parse_adr_text`, `_collect_headings`, `_extract_frontmatter_block`, `_partition_by_expiry`, `_match_repo_glob`) are the testability surface and MUST stay pure (no `datetime.now()`, no `Path.exists()`, no `open(...)`). The imperative shell (`async def run`) does the I/O. S6-01 / S6-02 established this discipline; S6-03 inherits it.
14. **`_PROBE_ID: Final[ProbeId]` is the typed identity surface.** `name: str = "<probe_id>"` satisfies the frozen Phase-0 `Probe` ABC; the module-level `_PROBE_ID` constant is the typed `NewType("ProbeId", str)` form for any consumer that needs newtype-strict probe identity (e.g., the registry's typed lookup). Precedent: `src/codegenie/probes/layer_b/scip_index.py:114`.
15. **Three-state confidence is the partial-success surface.** A repo with five ADR files where one has no `# H1` is NOT a marker-absent failure — it's `confidence="medium"` with `per_file_errors=("no_h1",)`. The operator reads the slice's `per_file_errors` and decides whether to fix the ADR or accept the partial index. Hiding partial failures behind `confidence="high"` (the original draft) would silently degrade Planner-side decisions downstream.
16. **`AdrId` newtype is NOT mandated.** This story has ONE concrete consumer of ADR identifiers (the slice's `id` field). Rule 2 (Simplicity First) says don't extract until the third concrete user arrives. If a Phase-3+ Planner adds `from codegenie.probes.layer_d.adrs import AdrId` for cross-module ID hygiene, the newtype lands then. For this story, `id: str` is sufficient.
17. **Possible Rule-of-Three triggers to watch on the next story:**
    - If S6-04 (`ExternalDocsProbe`) also needs a `safe_yaml.loads`-style in-memory parse, the chokepoint extension is justified at one consumer. If it adds a second pure-helper family (e.g., `_extract_frontmatter_block` reused), the helper extracts to `codegenie.parsers.frontmatter` at the third sibling.
    - If the three `_compute_confidence(items, errors)` copies (S6-01, S6-02, and the five copies in this story) get a fourth user (e.g., S6-04), the helper extracts to `codegenie.probes._common` or `codegenie.probes.confidence`.
    - The `MARKER_MODULES` parametrize list is the canonical extension point for sibling marker probes; adding a sixth probe is one line.
18. **The atomic raw-artifact write pattern.** Each probe writes `slice_.model_dump_json()` to `ctx.output_dir / "<probe_id>.json.tmp"` then `os.replace(tmp, final)` — atomic on POSIX. Avoid `open(final, "w")` direct writes; a crashed probe between truncate and flush would leave a corrupt JSON artifact that B2's index-health and S6-08's freshness checks would consume.
