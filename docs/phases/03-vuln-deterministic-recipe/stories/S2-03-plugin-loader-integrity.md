# Story S2-03 — Plugin loader: filesystem walk, `importlib`, `PLUGINS.lock` integrity check

**Step:** Step 2 — Plugin Registry kernel, manifest schema, loader, resolver
**Status:** Done — GREEN 2026-05-19 (phase-story-executor; see [`_attempts/S2-03.md`](_attempts/S2-03.md) for the per-AC evidence table + gate log)
**Effort:** M
**Depends on:** S1-01 (`PluginId`, `BlobDigest`, `parse_plugin_id`, `parse_blob_digest`), S1-03 (tagged-union outcomes), S2-01 (`PluginRegistry`, `default_registry`), S2-02 (`PluginManifest.from_yaml`)
**ADRs honored:** Phase 0 ADR-0001 (hashing chokepoint), Phase 1 ADR-0009 (`safe_json.load` chokepoint), ADR-0002 (registry kernel + exit 4), ADR-0010 (tagged-union sum types; newtypes), ADR-0011 (honest framing; Phase 11 substitution seam), production ADR-0031 (filesystem walk + `importlib`)

## Validation notes (2026-05-18 — HARDENED)

Validated via `phase-story-validator`. Full audit log: [`_validation/S2-03-plugin-loader-integrity.md`](_validation/S2-03-plugin-loader-integrity.md). Substantive changes vs. the `Ready` draft:

- **Chokepoint discipline restored.** Loader now routes hashing through `codegenie.hashing.tree_digest_of_files` (extending the ADR-0001 chokepoint, not bypassing it) and JSON reads through `codegenie.parsers.safe_json.load` (Phase 1 ADR-0009). Direct `hashlib` / `blake3` / `json` imports are AST-fence-forbidden in `loader.py`.
- **`PluginRejected` upgraded to tagged-union sum type** per ADR-0010 / S1-03. Seven dataclass variants (`IntegrityMismatch`, `MissingManifest`, `SchemaViolation`, `UnlockedPlugin`, `MissingPluginDirectory`, `PluginImportError`, `SymlinkEscape`); each carries only its evidence. `expected: BlobDigest` / `actual: BlobDigest` are mandatory on `IntegrityMismatch` (newtype, not `str`).
- **`PluginVerifier` Strategy seam introduced now** — ADR-0011 §Consequences line 78 explicitly pre-commits to the substitution interface `verify_plugin(plugin_dir) -> Result[None, VerificationError]` for Phase 11 Sigstore. `load_plugins(*, verifier=Sha256TreeDigestVerifier())` lets Phase 11 substitute via DI with zero edits to `loader.py`.
- **Verify-all-then-import-all order pinned by AC + witness test.** A tampered plugin's module body never runs even if other plugins' integrity passes. Closes the silent-registration mutation class.
- **Seven-variant rejection table is parametrized**; one named test per `PluginRejected` variant; one Hypothesis property test for digest walk-order invariance; one cross-platform LF/CRLF parametrize; one `__pycache__`-skip witness; one `sys.modules` witness for import-not-fired.
- **`CODEOWNERS` location corrected** to `.github/CODEOWNERS` (existing). Story previously said "repo root, create if absent" — would have created a duplicate.
- **`plugins/__init__.py` empty package marker added to Files-to-touch** so `importlib.import_module("plugins.{slug}.api")` resolves.
- **Functional-core / imperative-shell split.** `_collect_plugin_files(plugin_dir) -> Result[..., SymlinkEscape]` (impure) is separable from `tree_digest_of_files(pairs) -> BlobDigest` (pure, chokepoint-resident).
- **AST source-scan fence added** (`tests/static/test_plugins_loader_chokepoints.py`) so a future maintainer cannot accidentally re-add a direct `hashlib`/`json`/`blake3` import.

## Context

S2-01 lands the in-memory kernel; S2-02 lands the per-file manifest model. This story is the **bridge from disk to kernel**: the filesystem walk over `plugins/*/plugin.yaml`, the `importlib.import_module` invocation for each plugin's entry module (so the plugin's `@register_plugin(...)` call fires), and the per-plugin SHA-256 tree-digest verification against `plugins/PLUGINS.lock`. The integrity check is the structural enforcement of ADR-0011 — honestly framed as "catches accidental corruption and partial merges" (not "cryptographic signature"; Phase 11 ships Sigstore at this exact seam).

`plugins/PLUGINS.lock` ships **empty in Phase 3 / Step 2** (the first concrete plugin lands in Step 7 / S7-01). The loader must therefore handle the "lock file is empty" case as "no plugins to verify, walk finds zero plugins, registry is empty after load" — not as an error. The integrity check is the contract subsequent plugins commit to once they land. CODEOWNERS gates edits to `plugins/PLUGINS.lock` to the platform team (PR-template call-out), making the social anchor explicit.

The architectural shape is deliberately small: one `load_plugins(plugin_root, lock_path, *, registry=None, verifier=None) -> Result[LoadReport, PluginRejected]` entry point; one chokepoint hashing extension (`hashing.tree_digest_of_files`); one `LockFile` typed root-model; one `PluginVerifier` Protocol (defaulted to `Sha256TreeDigestVerifier`) so Phase 11's Sigstore swap is DI-only; one CODEOWNERS line. The loader does **not** validate scope or walk `extends` — that's the resolver (S2-04). Rejection is fail-fast; exit code 4 per ADR-0002.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2` — failure modes (`PluginRejected(integrity_mismatch)`, exit code 4) and the "loaded by the same mechanism" promise from ADR-0031.
  - `../phase-arch-design.md §Component design C10` paragraph on `SandboxedPath` — informs the tree-walk's path-discipline (no symlink-following during integrity hashing). Also §Edge cases E12 (TOCTOU is real).
  - `../phase-arch-design.md §Edge cases E10 + E17` — concrete-plugin `import_module` raises → `PluginRejected(import_error)`; SHA mismatch → `PluginRejected(integrity_mismatch)`.
  - `../phase-arch-design.md §Process view` — the loader runs once at orchestrator init; not in the hot path.
  - `../phase-arch-design.md §Patterns considered and deliberately rejected` line 951 — "No DI container" rationale (record but do not adopt).
- **Phase 3 ADRs:**
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — exit code 4 on collision/cycle/lock-mismatch; loader mutates the registry instance passed in (or `default_registry`).
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` §Decision 3 — tagged-union sum types on every state machine; the seven rejection variants ARE a state machine.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — `PLUGINS.lock` is integrity check, not signature; CODEOWNERS is the social anchor; **§Consequences line 78** explicitly names the Phase 11 substitution interface `verify_plugin(plugin_dir) -> Result[None, VerificationError]` — *this story exposes that interface now as a `PluginVerifier` Protocol parameter*.
- **Phase 0 / Phase 1 ADRs:**
  - `../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md` — `codegenie.hashing` is the **only** module under `src/codegenie/` allowed to import `hashlib.sha256` or `blake3`. The story's `tree_digest_of_files` extends this chokepoint additively.
  - `../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md` — `codegenie.parsers.safe_json.load` is the JSON chokepoint with `O_NOFOLLOW` + size cap + depth cap. `PLUGINS.lock` reads route through it.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Discovery and resolution — filesystem walk over `plugins/{slug}/plugin.yaml`; `importlib` triggers registration. §Plugin directory layout enumerates `probes/`, `adapters/`, `subgraph/`, etc. — no `api.py`. This story introduces the `api.py` entry-module convention (see Notes §7).
- **Existing code:**
  - `src/codegenie/probes/__init__.py` — explicit-imports precedent (no `importlib.metadata` entry-point scan; supply-chain hygiene). The plugin loader is the *opposite* shape — filesystem walk + dynamic import — but the **same hygiene principle**: never load from outside the repo.
  - `src/codegenie/hashing.py:1-29` — chokepoint discipline + the `sha256:<64-hex>` / `blake3:<64-hex>` prefix-tagged format. The new `tree_digest_of_files` returns un-prefixed 64-hex to match `BlobDigest` (`^[0-9a-f]{64}$`).
  - `src/codegenie/parsers/safe_json.py` — JSON chokepoint pattern.
  - `src/codegenie/parsers/_io.py` (`open_capped`) — the shared O_NOFOLLOW+size-cap primitive.
  - `src/codegenie/probes/deployment.py:183-193` — in-codebase `Path.resolve(strict=True).is_relative_to(root)` precedent.
  - `src/codegenie/plugins/manifest.py` (S2-02) — `PluginManifest.from_yaml(path)` returning `Result`.
  - `src/codegenie/plugins/registry.py` (S2-01) — the registry the loader mutates; `default_registry`.
  - `src/codegenie/plugins/errors.py` (S2-01) — `PluginRejected` placeholder lives here; this story replaces the placeholder with the tagged-union sum type.
  - `.github/CODEOWNERS:25-31` — existing CODEOWNERS file (this story edits it; does NOT create a duplicate at repo root).
- **Prior validation history (sibling-family lineage):**
  - `_validation/S1-03-tagged-union-outcomes.md` — the tagged-union pattern this story applies to `PluginRejected`.
  - `_validation/S2-01-plugin-registry-kernel.md` — `restore_default_registry` autouse fixture, parametrized per-variant tests, typed-`.name` exception payloads.
  - `_validation/S2-02-plugin-manifest-pydantic.md` — loader-with-tagged-union-errors family, route-through-chokepoint discipline, Hypothesis property for never-raises invariant.

## Goal

Ship a deterministic plugin loader that walks `plugins/`, **verifies every plugin's tree integrity against `plugins/PLUGINS.lock` BEFORE any plugin module is imported**, imports each verified plugin's entry module (firing `@register_plugin` side effects), and surfaces every failure mode as a typed `Result` over a tagged-union sum type. Route all hashing through the `codegenie.hashing` chokepoint and all JSON reads through the `codegenie.parsers.safe_json` chokepoint. Expose the verification step as a `PluginVerifier` Protocol so Phase 11 substitutes Sigstore via DI with zero edits to this loader. Ship an empty `PLUGINS.lock`, an empty `plugins/__init__.py` package marker, and an additive CODEOWNERS entry in `.github/CODEOWNERS`.

## Acceptance criteria

- [ ] **AC-1 — Public surface + LoadReport shape.** `src/codegenie/plugins/loader.py` exports `load_plugins(plugin_root: Path, lock_path: Path, *, registry: PluginRegistry | None = None, verifier: PluginVerifier | None = None) -> Result[LoadReport, PluginRejected]` and `compute_plugin_tree_digest(plugin_dir: Path) -> Result[BlobDigest, SymlinkEscape]`. `LoadReport` is a `BaseModel(frozen=True, extra="forbid")` with `loaded: tuple[PluginId, ...]` and `total_walked: int`.

- [ ] **AC-2 — Tree-digest is chokepoint-routed, deterministic, and binary-mode.** `compute_plugin_tree_digest` composes `_collect_plugin_files(plugin_dir) -> Result[tuple[tuple[str, bytes], ...], SymlinkEscape]` (impure: `sorted(plugin_dir.rglob("*"))`, skips `__pycache__/` and `*.pyc`, reads via `Path.read_bytes()`, refuses symlink-escape via `Path.resolve(strict=True).is_relative_to(plugin_dir.resolve(strict=True))`) with `codegenie.hashing.tree_digest_of_files(pairs: Iterable[tuple[str, bytes]]) -> BlobDigest` (pure given inputs; new public function added to `src/codegenie/hashing.py` — uses `hashlib.sha256` *inside* the chokepoint; returns un-prefixed 64-hex matching `BlobDigest`'s `^[0-9a-f]{64}$` regex via `parse_blob_digest`). **`loader.py` MUST NOT import `hashlib` or `blake3` directly** (enforced by AC-14 AST scan).

- [ ] **AC-3 — Empty-lock happy path.** `plugins/PLUGINS.lock` ships with content `{}` (empty JSON object) plus a sibling `plugins/PLUGINS.lock.README.md` explaining ADR-0011's honest framing and Step 7's first concrete entry. The loader's filesystem walk over `plugins/*/plugin.yaml` finds zero plugin directories and returns `Ok(LoadReport(loaded=(), total_walked=0))`. Mismatch on any plugin → `Err(IntegrityMismatch(plugin=name, expected=..., actual=...))`.

- [ ] **AC-4 — `PluginRejected` is a tagged-union sum type.** `src/codegenie/plugins/errors.py` defines seven frozen dataclass variants under `PluginRejected: TypeAlias = IntegrityMismatch | MissingManifest | SchemaViolation | UnlockedPlugin | MissingPluginDirectory | PluginImportError | SymlinkEscape`. Each variant has a `plugin: PluginId` field and a `kind: Literal[...]` discriminator; `IntegrityMismatch` additionally carries `expected: BlobDigest` and `actual: BlobDigest` (both mandatory — newtype, not `str | None`); `SchemaViolation` and `PluginImportError` additionally carry `detail: str`; `SymlinkEscape` additionally carries `offending_path: Path`. A free function `exit_code_for_rejection(p: PluginRejected) -> Literal[4]` is exported. A consumer-site `match` block with `assert_never` exhaustiveness check is included in TDD as a `mypy --strict` gate.

- [ ] **AC-5 — `LockFile` is a Pydantic `RootModel` routed through the `safe_json` chokepoint.** `src/codegenie/plugins/lockfile.py` defines `LockFile = RootModel[dict[PluginId, BlobDigest]]` with `LockFile.from_path(path: Path) -> Result[LockFile, LockFileMalformed]`. The implementation calls `codegenie.parsers.safe_json.load(path, max_bytes=1 << 16, max_depth=2, parser_kind="plugins_lock")`. Field validators lift `str` → `PluginId` via `parse_plugin_id` and `str` → `BlobDigest` via `parse_blob_digest`; failures are surfaced as `Err(LockFileMalformed(detail=...))`. Top-level non-object (`[]`, `null`, scalar) → `Err(LockFileMalformed(detail=...))`. **`loader.py` MUST NOT import `json` directly** (enforced by AC-14 AST scan).

- [ ] **AC-6 — `PluginVerifier` Protocol seam (ADR-0011 §Consequences line 78).** `src/codegenie/plugins/verifiers.py` declares `class PluginVerifier(Protocol): def verify(self, plugin_dir: Path, expected: BlobDigest) -> Result[None, VerificationError]: ...` and ships `class Sha256TreeDigestVerifier` implementing it via `compute_plugin_tree_digest`. `load_plugins(..., verifier=None)` defaults to `Sha256TreeDigestVerifier()`. A unit test (`test_load_plugins_accepts_alternate_verifier`) constructs a fake `PluginVerifier` whose `verify` returns `Ok(None)` regardless of expected digest, demonstrating Phase 11's substitution path with zero edits to `loader.py`.

- [ ] **AC-7 — Per-rejection parametrized tests.** `tests/unit/plugins/test_loader.py` carries a `@pytest.mark.parametrize` table covering one test per `PluginRejected` variant. Required test names:
  - `test_integrity_mismatch_returns_err` (the TDD red test)
  - `test_missing_manifest_returns_err`
  - `test_schema_violation_returns_err`
  - `test_unlocked_plugin_returns_err`
  - `test_missing_plugin_directory_returns_err`
  - `test_import_error_returns_err`
  - `test_symlink_escape_returns_err`
  Each asserts `result.is_err()`, the variant `isinstance(...)`, the `.plugin` field equals the expected `PluginId`, and `exit_code_for_rejection(err) == 4`.

- [ ] **AC-8 — Verify-all-then-import-all order is load-bearing.** `load_plugins` executes the four-gate pipeline in strict order across the entire plugin set:
  1. **Discover** — `sorted(plugin_root.glob("*/plugin.yaml"))` → `walked: tuple[Path, ...]`.
  2. **Verify** — load manifest (S2-02); reconcile manifest names against `LockFile` keys; for each (manifest, lock entry) call `verifier.verify(plugin_dir, expected=lock[name])`. Fail-fast on the first rejection.
  3. **Import** — only if every plugin passed Verify, call `importlib.import_module(f"plugins.{slug}.api")` for each in walk order. Fail-fast on the first `ImportError` → `PluginImportError`.
  4. **Register** — `@register_plugin` side effects from Import populate the registry.
  AC-12 supplies the witness test that no module is ever imported during a rejected load.

- [ ] **AC-9 — Fail-fast LoadReport semantics.** `LoadReport.loaded` reflects only plugins that passed both Verify AND Import (which, under AC-8, means either ALL plugins or NONE). `total_walked` is `len(walked)` regardless of outcome. On rejection, the function returns `Err(...)`; on success, `Ok(LoadReport(loaded=tuple(plugin_ids), total_walked=len(walked)))`.

- [ ] **AC-10 — Digest walk-order invariance (Hypothesis property).** `tests/unit/plugins/test_loader_digest_property.py` uses `@hypothesis.given(...)` to generate synthetic plugin trees (1–5 files, arbitrary names, arbitrary bytes) and asserts: `compute_plugin_tree_digest(plugin_dir) == compute_plugin_tree_digest(plugin_dir)` after each permutation of underlying `os.scandir` order (simulated by re-creating the tree with files written in shuffled order or by mocking `Path.rglob`). 30 runs minimum.

- [ ] **AC-11 — Cross-platform + `__pycache__` invariance.** `tests/unit/plugins/test_loader_digest_cross_platform.py` includes:
  - `test_digest_is_bytes_mode` parametrized over `b"line1\nline2"` and `b"line1\r\nline2"` content: writes the same logical content with LF then CRLF endings under different filenames; the digests differ (proves binary-mode read). The opposite mutant — text-mode read normalizing CRLF to LF — would make them equal and fail this test.
  - `test_digest_skips_pycache_directory`: compute digest, populate `plugin_dir/__pycache__/foo.cpython-311.pyc` with `b"bytecode"`, recompute, assert equality.
  - `test_digest_skips_pyc_files`: compute digest, populate `plugin_dir/leaked.pyc` at top level, recompute, assert equality.

- [ ] **AC-12 — Import-not-fired-on-rejection witness.** `tests/unit/plugins/test_loader.py::test_tampered_plugin_module_never_imported`: build a synthetic plugin whose `api.py` contains `import sys; sys.modules["__PROOF_OF_IMPORT__"] = object()`; lock its digest; tamper a sibling file; call `load_plugins`. Assertions: `result.is_err()`, `result.unwrap_err().kind == "integrity_mismatch"`, `"__PROOF_OF_IMPORT__" not in sys.modules`. Companion `test_no_partial_registration_on_any_rejection` parametrized across all seven `PluginRejected` variants asserts `registry.all() == ()` after every rejection path.

- [ ] **AC-13 — Default-registry path tested.** `tests/unit/plugins/test_loader.py::test_load_plugins_default_singleton_path` (with autouse `restore_default_registry` fixture from S2-01) invokes `load_plugins(plugin_root, lock_path)` with no `registry=` kwarg and asserts the resulting plugin appears in `default_registry.all()`. Teardown restores the snapshot.

- [ ] **AC-14 — AST source-scan fence.** `tests/static/test_plugins_loader_chokepoints.py` parses `src/codegenie/plugins/loader.py` with `ast.parse` and asserts no `Import` / `ImportFrom` node names `json`, `hashlib`, or `blake3`. Permitted imports include `codegenie.hashing`, `codegenie.parsers.safe_json`, `importlib`, `pathlib`. The fence is the structural enforcement of ADR-0001 + Phase 1 ADR-0009 at the new module's boundary.

- [ ] **AC-15 — CODEOWNERS + PR template.** `.github/CODEOWNERS` (existing file) gains a single additive line: `plugins/PLUGINS.lock @platform-team` (placeholder team handle — the implementer's commit message MUST carry a TODO asking the human reviewer to substitute the actual GitHub team handle). `.github/pull_request_template.md` (create if absent — keep additive) gets a call-out line: `If you changed plugins/PLUGINS.lock, confirm: plugin tree integrity recomputed; ADR-0011 honest-framing language preserved (integrity check, not signature).`

- [ ] **AC-16 — CLI exit-code class-attribute promise.** The orchestrator init in S6-04 maps any `PluginRejected` to exit code 4 via `exit_code_for_rejection(p)`. **This story does not own the CLI wire-up** but it does add a unit test asserting `exit_code_for_rejection(IntegrityMismatch(...)) == 4` (one assertion per variant, parametrized).

- [ ] **AC-17 — `ruff check`, `ruff format --check`, `mypy --strict` clean** on every touched file, INCLUDING the `match`/`assert_never` consumer-site test that gates exhaustiveness at type-check time.

## Implementation outline

1. **Extend `src/codegenie/hashing.py`** (additive, chokepoint-respecting):
   ```python
   def tree_digest_of_files(pairs: Iterable[tuple[str, bytes]]) -> BlobDigest:
       """Pure SHA-256 tree-digest over (relpath, file_bytes) pairs.

       Caller MUST pre-sort and pre-filter. Each pair is serialized as
       ``<relpath>\\x1f<size>\\x1f<bytes>`` and records are joined by
       ``\\x1e`` — the same separator discipline as ``content_hash_of_inputs``.
       Returns un-prefixed 64-hex BlobDigest (S1-01 newtype regex).
       """
   ```
   This is the **only** new place `hashlib.sha256` is read; the chokepoint stays one-file-thick.

2. **Create `src/codegenie/plugins/lockfile.py`**:
   - `class LockFile(RootModel[dict[PluginId, BlobDigest]])` with `field_validator`s lifting raw `dict[str, str]` via `parse_plugin_id` + `parse_blob_digest`.
   - `LockFile.from_path(path: Path) -> Result[LockFile, LockFileMalformed]` — calls `codegenie.parsers.safe_json.load(path, max_bytes=1<<16, max_depth=2, parser_kind="plugins_lock")`; top-level non-object → `Err`.
   - `class LockFileMalformed` — frozen dataclass with `detail: str`.

3. **Create `src/codegenie/plugins/verifiers.py`** (the ADR-0011 §Consequences line 78 Strategy seam):
   ```python
   class PluginVerifier(Protocol):
       def verify(self, plugin_dir: Path, expected: BlobDigest) -> Result[None, VerificationError]: ...

   @dataclass(frozen=True)
   class VerificationError:
       plugin_dir: Path
       expected: BlobDigest
       actual: BlobDigest

   @dataclass(frozen=True)
   class Sha256TreeDigestVerifier:
       def verify(self, plugin_dir: Path, expected: BlobDigest) -> Result[None, VerificationError]:
           match compute_plugin_tree_digest(plugin_dir):
               case Ok(actual) if actual == expected: return Ok(None)
               case Ok(actual): return Err(VerificationError(plugin_dir, expected, actual))
               case Err(symlink_escape): return Err(VerificationError(plugin_dir, expected, actual=BlobDigest("0"*64)))
   ```
   Phase 11 lands `SigstoreVerifier` as a new file + DI swap; zero edits to `loader.py`.

4. **Extend `src/codegenie/plugins/errors.py`** — replace the S2-01 `PluginRejected` placeholder with the seven-variant tagged-union per AC-4. Add `exit_code_for_rejection(p: PluginRejected) -> Literal[4]`.

5. **Create `src/codegenie/plugins/loader.py`**:
   - `_collect_plugin_files(plugin_dir: Path) -> Result[tuple[tuple[str, bytes], ...], SymlinkEscape]`: impure walk + symlink-discipline + `__pycache__`/`*.pyc` skip + `Path.read_bytes()`.
   - `compute_plugin_tree_digest(plugin_dir: Path) -> Result[BlobDigest, SymlinkEscape]`: composes `_collect_plugin_files` with `codegenie.hashing.tree_digest_of_files`.
   - `load_plugins(plugin_root, lock_path, *, registry=None, verifier=None) -> Result[LoadReport, PluginRejected]` executes the four-gate pipeline (AC-8):
     1. **Discover** — `walked = sorted(plugin_root.glob("*/plugin.yaml"))`.
     2. **Verify** — load `LockFile.from_path(lock_path)`; for each walked manifest, load via `PluginManifest.from_yaml` (route `Err` → `SchemaViolation` or `MissingManifest`); verify `manifest.name in lock`; call `verifier.verify(plugin_dir, expected=lock[name])`. Cross-check: every entry in `lock` was visited; missing dir → `MissingPluginDirectory`. Fail-fast on first rejection.
     3. **Import** — only if Verify passed for ALL plugins, call `importlib.import_module(f"plugins.{slug}.api")` in walk order. Catch and reroute to `PluginImportError`.
     4. **Return** `Ok(LoadReport(loaded=tuple(plugin_ids), total_walked=len(walked)))`.

6. **Create supporting files**:
   - `plugins/__init__.py` — empty package marker (required for `importlib.import_module("plugins.{slug}.api")` to resolve).
   - `plugins/PLUGINS.lock` — content `{}`.
   - `plugins/PLUGINS.lock.README.md` — one-paragraph ADR-0011 honest-framing note + Step 7 forward pointer.
   - `.github/CODEOWNERS` — additive line `plugins/PLUGINS.lock @platform-team` (TODO in commit message: confirm team handle).
   - `.github/pull_request_template.md` — call-out per AC-15 (additive; create if absent).

7. **Tests**:
   - `tests/unit/plugins/test_loader.py` — TDD red + parametrized per-variant rejections + import-not-fired witness + default-registry path.
   - `tests/unit/plugins/test_loader_digest_property.py` — Hypothesis walk-order invariance.
   - `tests/unit/plugins/test_loader_digest_cross_platform.py` — binary-mode + pycache-skip witnesses.
   - `tests/unit/plugins/test_loader_empty.py` — empty-lock + zero-plugins happy path.
   - `tests/static/test_plugins_loader_chokepoints.py` — AST source-scan fence (AC-14).
   - `tests/fixtures/plugins/loader_fixtures.py` — `make_fake_plugin_dir(name, body=...)` helper.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/plugins/test_loader.py`

```python
import re
import sys
from pathlib import Path

from codegenie.plugins.errors import IntegrityMismatch, exit_code_for_rejection
from codegenie.plugins.loader import compute_plugin_tree_digest, load_plugins
from codegenie.plugins.lockfile import LockFile
from codegenie.plugins.registry import PluginRegistry
from codegenie.types.identifiers import PluginId


def test_integrity_mismatch_returns_err(tmp_path: Path):
    """ADR-0011: `PLUGINS.lock` mismatch is a typed `IntegrityMismatch` variant
    with exit code 4. Mutate a plugin file after locking; loader must refuse
    AND must NOT import the tampered module."""
    plugin_root = tmp_path / "plugins"
    slug_dir = plugin_root / "example--noop--npm"
    slug_dir.mkdir(parents=True)
    (slug_dir / "plugin.yaml").write_text(
        "name: example--noop--npm\nversion: 0.1.0\n"
        "scope:\n  task_class: example\n  languages: ['*']\n  build_systems: ['*']\n"
        "contributes:\n  tccm: ./tccm.yaml\n",
        encoding="utf-8",
    )
    (slug_dir / "api.py").write_text("# initial body\n", encoding="utf-8")

    # Snapshot the digest using the loader's own helper, then mutate AFTER locking.
    locked = compute_plugin_tree_digest(slug_dir).unwrap()
    # Pin the BlobDigest format — un-prefixed lowercase 64-hex per S1-01.
    assert re.fullmatch(r"[0-9a-f]{64}", locked)

    lock_path = plugin_root / "PLUGINS.lock"
    lock_path.write_text(f'{{"example--noop--npm": "{locked}"}}', encoding="utf-8")
    (slug_dir / "api.py").write_text("# tampered body\n", encoding="utf-8")

    sys.modules.pop("__PROOF_OF_IMPORT__", None)
    registry = PluginRegistry()
    result = load_plugins(plugin_root, lock_path, registry=registry)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, IntegrityMismatch)
    assert err.plugin == PluginId("example--noop--npm")
    assert exit_code_for_rejection(err) == 4
    assert len(registry.all()) == 0
    # The tampered module must NOT have been imported — verify-then-import order.
    assert "__PROOF_OF_IMPORT__" not in sys.modules
```

Why it fails: `codegenie.plugins.loader`, `lockfile`, `verifiers` do not yet exist; `IntegrityMismatch` is unpopulated; `tree_digest_of_files` is not extended onto `hashing.py`.

### Green follow-on tests (each is a separate, named test)

Listed in the order the executor implements them:

1. `test_missing_manifest_returns_err` — `plugins/{slug}/` directory exists but no `plugin.yaml`. → `Err(MissingManifest(plugin=PluginId(slug)))`.
2. `test_schema_violation_returns_err` — malformed `plugin.yaml` (per S2-02's `from_yaml`). → `Err(SchemaViolation(plugin=PluginId(slug), detail=...))`.
3. `test_unlocked_plugin_returns_err` — manifest names a plugin not in `PLUGINS.lock`. → `Err(UnlockedPlugin(plugin=...))`.
4. `test_missing_plugin_directory_returns_err` — `PLUGINS.lock` entry exists but no matching directory. → `Err(MissingPluginDirectory(plugin=...))`.
5. `test_import_error_returns_err` — `api.py` raises at import time (e.g., `raise RuntimeError("boom")`). → `Err(PluginImportError(plugin=..., detail=...))`.
6. `test_symlink_escape_returns_err` — `plugins/{slug}/escape.py` is a symlink pointing OUT of `plugin_dir`. → `Err(SymlinkEscape(plugin=..., offending_path=...))`.
7. `test_malformed_lock_returns_err` — `PLUGINS.lock` content is `[]` / `null` / scalar → `Err(LockFileMalformed(...))` from `LockFile.from_path` (lifted into the loader's `Result`).
8. `test_no_partial_registration_on_any_rejection` — parametrized across all 7 `PluginRejected` variants; asserts `registry.all() == ()` after each rejection path.
9. `test_tampered_plugin_module_never_imported` — see AC-12. Witness: `sys.modules["__PROOF_OF_IMPORT__"]` is never set.
10. `test_load_plugins_default_singleton_path` — `load_plugins(plugin_root, lock_path)` with no `registry=` kwarg; autouse `restore_default_registry` fixture from S2-01's `conftest.py`.
11. `test_load_plugins_accepts_alternate_verifier` — pass a fake `PluginVerifier` whose `verify` returns `Ok(None)` regardless; loader proceeds to Import even with a mismatched lock entry. Demonstrates Phase 11 substitutability.
12. `test_lockfile_roundtrip` — write `{"a--b--c": "0"*64}`, load via `LockFile.from_path`, assert `lockfile.root[PluginId("a--b--c")] == BlobDigest("0"*64)`.
13. `test_empty_lock_zero_plugins` (in `test_loader_empty.py`) — empty `PLUGINS.lock` + empty `plugins/` → `Ok(LoadReport(loaded=(), total_walked=0))`.
14. Hypothesis property in `test_loader_digest_property.py` — see AC-10.
15. Cross-platform witnesses in `test_loader_digest_cross_platform.py` — see AC-11.
16. AST fence in `tests/static/test_plugins_loader_chokepoints.py` — see AC-14.
17. `exit_code_for_rejection` parametrized smoke — see AC-16.

### Refactor

- Pull each error branch in `load_plugins` into a small `_reject(variant)` helper so the main loop reads top-down with no nested try/except.
- A consumer-site `match` block over `PluginRejected` with `assert_never` in the default arm; placed in a `test_pluginrejected_exhaustiveness_gate` test that exists only to make `mypy --strict` fail if a new variant lands without updating consumers.
- Document symlink-refusal explicitly (TOCTOU-adjacent — ADR-0011 framing).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/hashing.py` | Additive `tree_digest_of_files(pairs) -> BlobDigest` extension of the ADR-0001 chokepoint. |
| `src/codegenie/plugins/loader.py` | The loader entry point + `_collect_plugin_files` + `compute_plugin_tree_digest`. |
| `src/codegenie/plugins/lockfile.py` | `LockFile = RootModel[dict[PluginId, BlobDigest]]` routed through `safe_json.load`. |
| `src/codegenie/plugins/verifiers.py` | `PluginVerifier` Protocol + `Sha256TreeDigestVerifier` (ADR-0011 §Consequences line 78 substitution seam). |
| `src/codegenie/plugins/errors.py` | Replace the S2-01 `PluginRejected` placeholder with the 7-variant tagged-union sum type + `exit_code_for_rejection`. |
| `plugins/__init__.py` | Empty package marker so `importlib.import_module("plugins.{slug}.api")` resolves. |
| `plugins/PLUGINS.lock` | Empty JSON `{}`; ships in this story. |
| `plugins/PLUGINS.lock.README.md` | One-paragraph honest-framing note (ADR-0011) + Step 7 forward pointer. |
| `.github/CODEOWNERS` | Additive line `plugins/PLUGINS.lock @platform-team` (existing file — do NOT create at repo root). |
| `.github/pull_request_template.md` | Call-out for `PLUGINS.lock` edits (additive; create if absent). |
| `tests/unit/plugins/test_loader.py` | TDD red + every `PluginRejected` variant + import-not-fired witness + default-registry path. |
| `tests/unit/plugins/test_loader_empty.py` | Empty-lock + zero-plugins happy path. |
| `tests/unit/plugins/test_loader_digest_property.py` | Hypothesis walk-order invariance (AC-10). |
| `tests/unit/plugins/test_loader_digest_cross_platform.py` | Binary-mode + `__pycache__` / `*.pyc` skip witnesses (AC-11). |
| `tests/static/test_plugins_loader_chokepoints.py` | AST fence asserting `loader.py` does not import `json`/`hashlib`/`blake3` (AC-14). |
| `tests/fixtures/plugins/loader_fixtures.py` | `make_fake_plugin_dir(name, body=...)` helper. |

## Out of scope

- **Resolver / `extends` walking / specificity / precedence sort** — handled by S2-04.
- **Concrete plugin tree under `plugins/vulnerability-remediation--node--npm/`** — handled by S7-01. This story ships the loader against synthetic fixture trees only.
- **Sigstore signing (real cryptographic verification)** — Phase 11 substitutes `SigstoreVerifier` at this loader's `PluginVerifier` interface; no edits to `loader.py` required at that time. ADR-0011 §Consequences line 78.
- **Alternate entry-module names.** Phase 3 fixes the convention to `plugins/{slug}/api.py`. A future manifest-schema amendment may add an `entry_module: str = "api"` field if a plugin needs a different name; deferred until a concrete plugin requires it.
- **CLI exit-code wiring** — the orchestrator init in S6-04 maps `PluginRejected` to exit 4 via `exit_code_for_rejection`. This story exposes the function; S6-04 consumes it.
- **`PluginExtendsCycle` detection** — that's a resolver concern (S2-04). The loader does no graph analysis.
- **Lock-file regeneration tooling** — `codegenie plugins lock-update` CLI is named in phase-arch E17 recovery column; deferred to Phase 11 alongside Sigstore.
- **Concurrent loader invocation / module-reload semantics** — single-process Phase-3 assumption; Phase 11 `--reload-plugins` is the seam.

## Notes for the implementer

1. **The empty-lock invariant is load-bearing.** A future maintainer might be tempted to "guard against the empty case as bad config." Don't — `{}` is the intentional state from Step 2 through Step 6. The first non-empty entry lands in S7-01 with `vulnerability-remediation--node--npm`.

2. **Honest-framing language is structural, not docs.** Per ADR-0011: do not name the function `verify_signature` or use the word "signature" anywhere in this module. Use "integrity check" / "tree digest" everywhere. `IntegrityMismatch` not `SignatureFailure`. The CODEOWNERS line + PR template + `PLUGINS.lock.README.md` all preserve this language.

3. **Loader pipeline — four gates, fail-fast at each.**
   - **Discover** → `Verify` → `Import` → `Register`.
   - **Verify ALL** before importing **ANY**. This is the AC-8 invariant. A per-plugin "verify then import" loop is wrong: it allows a verified plugin's module-body to run before a *later* plugin's integrity check fails, leaving the registry partially mutated for the discarded run.
   - Fail-fast at each gate; the four-gate boundary is what the witness tests (AC-12) defend.

4. **Phase 11 substitution seam (`PluginVerifier`) is an explicit pre-commitment.** ADR-0011 §Consequences line 78 names this interface verbatim. Do not inline the SHA-256 verification inside `load_plugins`; route it through the Protocol parameter. The cost is one extra file (`verifiers.py`) and one parameter; the benefit is that Phase 11's Sigstore work is a new file plus a DI substitution at the CLI entry point — zero edits to `loader.py`. This is the canonical Plugin / Strategy / Open-Closed pattern and the ADR has already paid the design cost.

5. **Functional-core / imperative-shell split.** `_collect_plugin_files` does the filesystem I/O (walk + read + symlink-check). `codegenie.hashing.tree_digest_of_files` is the pure hashing core. `compute_plugin_tree_digest` is the public composition. This makes the Hypothesis property test (AC-10) trivially expressive: generate `(path, bytes)` pairs, shuffle, assert digest equality — no temp-dir fixtures required at the inner layer.

6. **Chokepoint discipline.** `codegenie.hashing` is the **only** place under `src/codegenie/` allowed to import `hashlib.sha256` / `blake3` (Phase 0 ADR-0001). `codegenie.parsers.safe_json` is the **only** place allowed to call `json.loads` (Phase 1 ADR-0009). Direct `hashlib`, `blake3`, or `json` imports in `loader.py` are AST-fence-forbidden by AC-14. If a reviewer asks "why not just `hashlib.sha256()` here, it's three lines" — the answer is the chokepoint kernel pattern; future migration to a different hash (Phase 11 Sigstore) flips one file, not seven.

7. **Entry-module convention (`api.py`) + `plugins/__init__.py`.** Production ADR-0031 §Plugin directory layout enumerates `probes/`, `adapters/`, `subgraph/`, etc. — no `api.py`. Phase 3 introduces `plugins/{slug}/api.py` as the registration entry-module convention. The implementer adds an empty `plugins/__init__.py` so `importlib.import_module("plugins.{slug}.api")` resolves. If a later plugin needs a different entry-module name, amend the manifest schema (deferred — see Out-of-scope).

8. **CODEOWNERS placeholder discipline.** Edit `.github/CODEOWNERS` (existing); do NOT create a duplicate at repo root. Use `@platform-team` if the actual GitHub team handle is unknown at story-implementation time; leave a TODO in the commit message asking the human reviewer to substitute the correct handle. Do not invent a handle.

9. **Deliberately not adopted.**
   - **No DI container** (matches phase-arch §"Patterns considered and deliberately rejected" line 951). The single `verifier` parameter is sufficient DI.
   - **No `entry_module` field on the manifest in Phase 3.** Rule 2 — three concrete consumers haven't materialized; convention `api.py` carries us until S7-01.
   - **No `SigstoreVerifier` here.** The Protocol seam is enough; Phase 11 ships the concrete implementation.
   - **No concurrent-load support.** Single-process assumption; Phase 11 `--reload-plugins` is the seam.

10. **Symbol references.** S2-01's `PluginRegistry.register(plugin) -> Plugin` (per its validation report) is the source of truth — consume what S2-01 shipped, not what phase-arch C2 line 466 named. `default_registry` is the module-level `Final` instance per ADR-0002.

11. **Symlink discipline.** `_collect_plugin_files` uses `Path.resolve(strict=True).is_relative_to(plugin_dir.resolve(strict=True))`. A symlink that points *inside* the plugin dir is fine; a symlink that escapes returns `Err(SymlinkEscape(plugin=PluginId(slug), offending_path=resolved))`. The check mirrors `src/codegenie/probes/deployment.py:183-193`.

12. **`LoadReport` is minimal.** `loaded: tuple[PluginId, ...]`, `total_walked: int`. Resist adding `timings: ...` etc. — that's bench-harness territory (S9-03).
