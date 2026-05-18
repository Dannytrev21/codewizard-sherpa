# Story S2-03 — Plugin loader: filesystem walk, `importlib`, `PLUGINS.lock` integrity check

**Step:** Step 2 — Plugin Registry kernel, manifest schema, loader, resolver
**Status:** Ready
**Effort:** M
**Depends on:** S2-01
**ADRs honored:** ADR-0002, ADR-0011, production ADR-0031

## Context

S2-01 lands the in-memory kernel; S2-02 lands the per-file manifest model. This story is the **bridge from disk to kernel**: the filesystem walk over `plugins/*/plugin.yaml`, the `importlib.import_module` invocation for each plugin's entry module (so the plugin's `@register_plugin(...)` call fires), and the per-plugin SHA-256 tree-hash verification against `plugins/PLUGINS.lock`. The integrity check is the structural enforcement of ADR-0011 — honestly framed as "catches accidental corruption and partial merges" (not "cryptographic signature"; Phase 11 ships Sigstore at this exact seam).

`plugins/PLUGINS.lock` ships **empty in Phase 3 / Step 2** (the first concrete plugin lands in Step 7 / S7-01). The loader must therefore handle the "lock file is empty" case as "no plugins to verify, walk finds zero plugins, registry is empty after load" — not as an error. The integrity check is the contract subsequent plugins commit to once they land. CODEOWNERS gates edits to `plugins/PLUGINS.lock` to the platform team (PR-template call-out), making the social anchor explicit.

The architectural shape is deliberately small: one `load_plugins(plugin_root, lock_path, *, registry=None) -> Result[LoadReport, PluginRejected]` entry point; one tree-hash helper; one CODEOWNERS line. The loader does **not** validate scope or walk `extends` — that's the resolver (S2-04). Mismatch is the only fatal case; exit code 4 per ADR-0002.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C2` — failure modes (`PluginRejected(integrity_mismatch)`, exit code 4) and the "loaded by the same mechanism" promise from ADR-0031.
  - `../phase-arch-design.md §Component design — `C10` paragraph on `SandboxedPath` — informs the tree-walk's path-discipline (no symlink-following during integrity hashing).
  - `../phase-arch-design.md §Edge cases` — empty `PLUGINS.lock` (no plugins to verify), missing manifest, malformed YAML, lock mismatch.
  - `../phase-arch-design.md §Process view` — the loader runs once at orchestrator init; not in the hot path.
- **Phase ADRs:**
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — ADR-0002 — exit code 4 on collision/cycle/lock-mismatch; loader mutates the registry instance passed in (or `default_registry`).
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — ADR-0011 — `PLUGINS.lock` is integrity check, not signature; CODEOWNERS is the social anchor; Phase 11 substitutes Sigstore at the loader interface (`verify_plugin(plugin_dir) -> Result[None, VerificationError]`).
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Discovery and resolution — filesystem walk over `plugins/{slug}/plugin.yaml`; `importlib` triggers registration.
- **Existing code:**
  - `src/codegenie/probes/__init__.py` — explicit-imports precedent (no `importlib.metadata` entry-point scan; supply-chain hygiene). The plugin loader is the *opposite* shape — filesystem walk + dynamic import — but the **same hygiene principle**: never load from outside the repo.
  - `src/codegenie/hashing.py` — existing hashing helpers; reuse the canonicalization functions.
  - `src/codegenie/plugins/manifest.py` (S2-02) — `PluginManifest.from_yaml(path)` returning `Result`.
  - `src/codegenie/plugins/registry.py` (S2-01) — the registry the loader mutates.
  - `src/codegenie/plugins/errors.py` (S2-01) — `PluginRejected` placeholder lives here; this story populates the `integrity_mismatch` variant.

## Goal

Ship a deterministic plugin loader that walks `plugins/`, validates per-plugin tree integrity against `plugins/PLUGINS.lock`, imports each plugin's entry module (firing `@register_plugin` side effects), and surfaces every failure mode as a typed `Result`. Ship an empty `PLUGINS.lock` and the CODEOWNERS entry that gates its edits.

## Acceptance criteria

- [ ] `src/codegenie/plugins/loader.py` exports `load_plugins(plugin_root: Path, lock_path: Path, *, registry: PluginRegistry | None = None) -> Result[LoadReport, PluginRejected]` and `compute_plugin_tree_digest(plugin_dir: Path) -> BlobDigest`.
- [ ] `compute_plugin_tree_digest` is deterministic: sorts file paths, hashes `(relative_path, file_bytes)` pairs into a single SHA-256, returns a `BlobDigest`. Skips `__pycache__/` and `.pyc` files. Refuses to follow symlinks (path is canonicalized; non-relative-to-`plugin_dir` raises).
- [ ] `PLUGINS.lock` is a JSON file mapping `{plugin_name: hex_sha256}`. Empty `{}` is valid and means "no plugins to verify"; the loader's filesystem walk over `plugins/*/plugin.yaml` then expects to find zero plugin directories and emits a `LoadReport(loaded=[], total_walked=0)`. Mismatch on any plugin → `Err(PluginRejected(reason="integrity_mismatch", plugin=name, expected=..., actual=...))`.
- [ ] Loader behavior is total for every documented edge case:
  - Missing `plugin.yaml` in a `plugins/{slug}/` directory → `Err(PluginRejected(reason="missing_manifest", plugin=slug))`.
  - Malformed `plugin.yaml` (S2-02's `from_yaml` returns `Err`) → `Err(PluginRejected(reason="schema_violation", plugin=slug, detail=...))`.
  - Plugin name in `plugin.yaml` not listed in `PLUGINS.lock` → `Err(PluginRejected(reason="unlocked_plugin", plugin=name))`.
  - Plugin listed in `PLUGINS.lock` but no matching directory → `Err(PluginRejected(reason="missing_plugin_directory", plugin=name))`.
  - `importlib.import_module(plugin_entry)` raises → `Err(PluginRejected(reason="import_error", plugin=name, detail=...))`.
  - SHA-256 mismatch → `Err(PluginRejected(reason="integrity_mismatch", plugin=name))`.
- [ ] `plugins/PLUGINS.lock` file ships with content `{}` (empty JSON object) plus a one-line comment header in a sibling `plugins/PLUGINS.lock.README.md` explaining ADR-0011's honest framing and Step 7's first concrete entry.
- [ ] `CODEOWNERS` (repo root) gains an entry: `plugins/PLUGINS.lock @platform-team` (placeholder team handle — record the actual team name in the implementer's commit). PR template (`.github/pull_request_template.md` if present, else create) gets a call-out line: "If you changed `plugins/PLUGINS.lock`, confirm: plugin tree integrity recomputed; ADR-0011 honest-framing language preserved."
- [ ] `tests/unit/plugins/test_loader.py` covers every failure mode (one test per `PluginRejected.reason`); `tests/unit/plugins/test_loader_empty.py` asserts the empty-lock + zero-plugins happy path.
- [ ] TDD red test (`test_integrity_mismatch_returns_err`) committed and green.
- [ ] CLI exit-code wiring: the entry-point that invokes `load_plugins` (orchestrator init — wired in S6-04) maps any `PluginRejected` to exit code 4. **This story does not own the CLI wire-up** but it does add a unit test asserting `PluginRejected.exit_code == 4` is exposed as a class attribute / method that S6-04 will consume.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on touched files.

## Implementation outline

1. Extend `src/codegenie/plugins/errors.py` (`PluginRejected` placeholder from S2-01): add the `reason` Literal taxonomy, `plugin: PluginId`, optional `detail: str | None`, optional `expected`/`actual` digest fields, and `exit_code: ClassVar[int] = 4`.
2. Create `src/codegenie/plugins/loader.py`:
   - `compute_plugin_tree_digest(plugin_dir: Path) -> BlobDigest`: `sorted(plugin_dir.rglob("*"))`, skip `__pycache__`/`*.pyc`, canonicalize paths, refuse symlinks (`Path.resolve(strict=True)` + `is_relative_to(plugin_dir)`), feed `(relpath, bytes)` pairs into a `hashlib.sha256()`.
   - `_read_lock(lock_path: Path) -> dict[PluginId, BlobDigest]`: small JSON loader; empty `{}` is the Phase-3 default.
   - `load_plugins(plugin_root, lock_path, *, registry=None) -> Result[LoadReport, PluginRejected]`:
     1. `lock = _read_lock(lock_path)`.
     2. `walked = sorted(plugin_root.glob("*/plugin.yaml"))`.
     3. For each walked manifest path: load via `PluginManifest.from_yaml` (route `Err` → `PluginRejected`).
     4. Verify `manifest.name` is in `lock`; otherwise `unlocked_plugin`.
     5. Compute the plugin-dir digest; compare to `lock[name]`; mismatch → `integrity_mismatch`.
     6. `importlib.import_module(f"plugins.{slug}.api")` (the convention from production ADR-0031 §Plugin directory layout); catch and reroute.
     7. Once every plugin has imported, return `Ok(LoadReport(loaded=[...], total_walked=len(walked)))`.
     8. Cross-check: every entry in `lock` was visited; missing dirs → `missing_plugin_directory`.
3. Create `plugins/PLUGINS.lock` with content `{}`. Create `plugins/PLUGINS.lock.README.md` linking ADR-0011.
4. Update root `CODEOWNERS` (create if absent) with the gating line.
5. Update `.github/pull_request_template.md` with the call-out (create if absent — keep additive).
6. Tests: a tmp-dir-based fixture builds synthetic plugin trees (with `make_fake_plugin_dir(name, body=...)` helper), invokes `load_plugins`, asserts each rejection variant.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/unit/plugins/test_loader.py`

```python
import hashlib
import json
from pathlib import Path

from codegenie.plugins.errors import PluginRejected
from codegenie.plugins.loader import compute_plugin_tree_digest, load_plugins
from codegenie.plugins.registry import PluginRegistry


def test_integrity_mismatch_returns_err(tmp_path: Path):
    """ADR-0011: `PLUGINS.lock` mismatch is a typed `PluginRejected(integrity_mismatch)`
    with exit code 4. Mutate a plugin file after locking; loader must refuse."""
    plugin_root = tmp_path / "plugins"
    slug_dir = plugin_root / "example--noop--npm"
    slug_dir.mkdir(parents=True)
    (slug_dir / "plugin.yaml").write_text(
        "name: example--noop--npm\n"
        "version: 0.1.0\n"
        "scope:\n"
        "  task_class: example\n"
        "  languages: ['*']\n"
        "  build_systems: ['*']\n"
        "contributes:\n"
        "  tccm: ./tccm.yaml\n",
        encoding="utf-8",
    )
    (slug_dir / "api.py").write_text("# initial body\n", encoding="utf-8")

    # Snapshot the digest, then mutate the plugin AFTER locking.
    locked_digest = compute_plugin_tree_digest(slug_dir)
    lock_path = plugin_root / "PLUGINS.lock"
    lock_path.write_text(json.dumps({"example--noop--npm": locked_digest}), encoding="utf-8")

    (slug_dir / "api.py").write_text("# tampered body\n", encoding="utf-8")

    registry = PluginRegistry()
    result = load_plugins(plugin_root, lock_path, registry=registry)
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, PluginRejected)
    assert err.reason == "integrity_mismatch"
    assert err.plugin == "example--noop--npm"
    assert err.exit_code == 4
    assert len(registry.all()) == 0  # tampered plugin MUST NOT register
```

Why it fails: `codegenie.plugins.loader` does not exist; `compute_plugin_tree_digest` and `load_plugins` are not defined.

### Green — minimal pass

- Implement `compute_plugin_tree_digest` with the canonicalization above.
- Implement `load_plugins` with the seven-step flow.
- Extend `PluginRejected` with `reason`, `exit_code = 4`, `plugin`, `detail`.

### Refactor

- Pull each error branch into a small `_reject(reason, ..., return_early=True)` helper so the main loop reads top-down with no nested try/except.
- Document the symlink-refusal explicitly (TOCTOU-adjacent — ADR-0011 framing).
- Add property test (optional): `compute_plugin_tree_digest` is invariant under directory traversal order (any `os.walk` order yields the same digest because we sort).
- Cross-platform: file mode bits and line endings must not affect the digest. Hash file *bytes* exactly; don't read in text mode.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/loader.py` | The loader entry point + tree-digest helper. |
| `src/codegenie/plugins/errors.py` | Flesh out `PluginRejected` with reason taxonomy and `exit_code = 4`. |
| `plugins/PLUGINS.lock` | Empty JSON `{}`; ships in this story. |
| `plugins/PLUGINS.lock.README.md` | One-paragraph honest-framing note (ADR-0011) + Step 7 forward pointer. |
| `CODEOWNERS` | `plugins/PLUGINS.lock @platform-team` gating line (create if absent). |
| `.github/pull_request_template.md` | Call-out for `PLUGINS.lock` edits (additive; create if absent). |
| `tests/unit/plugins/test_loader.py` | TDD red + every `PluginRejected.reason` variant. |
| `tests/unit/plugins/test_loader_empty.py` | Empty-lock + zero-plugins happy path. |
| `tests/fixtures/plugins/loader_fixtures.py` | `make_fake_plugin_dir(name, body=...)` helper. |

## Out of scope

- **Resolver / `extends` walking / specificity / precedence sort** — handled by S2-04.
- **Concrete plugin tree under `plugins/vulnerability-remediation--node--npm/`** — handled by S7-01. This story ships the loader against synthetic fixture trees only.
- **Sigstore signing (real cryptographic verification)** — Phase 11 substitutes the verifier at this loader's interface. The signature *field* on the manifest (S2-02) is decorative until then.
- **CLI exit-code wiring** — the orchestrator init in S6-04 maps `PluginRejected` to exit 4. This story exposes `exit_code` as a class attribute and asserts it; S6-04 consumes it.
- **`PluginExtendsCycle` detection** — that's a resolver concern (S2-04). The loader does no graph analysis.

## Notes for the implementer

- The empty-lock invariant is load-bearing. A future maintainer might be tempted to "guard against the empty case as bad config." Don't — `{}` is the intentional state from Step 2 through Step 6. The first non-empty entry lands in S7-01 with `vulnerability-remediation--node--npm`.
- ADR-0011's honest framing is **not just docs** — it's structural. Do not name the function `verify_signature` or use the word "signature" anywhere in this module. Use "integrity check" / "tree digest" everywhere. `PluginRejected(reason="integrity_mismatch")` not `PluginRejected(reason="signature_failure")`.
- Symlink discipline: `compute_plugin_tree_digest` must refuse to follow symlinks out of the plugin directory. The check is `path.resolve(strict=True).is_relative_to(plugin_dir.resolve(strict=True))`. A symlink that points *inside* the plugin dir is fine; a symlink that escapes is a `Err(PluginRejected(reason="symlink_escape", plugin=name))` (this isn't in the AC list — add it if the implementation hits it in practice; otherwise, defer).
- The `importlib.import_module(f"plugins.{slug}.api")` call assumes the repo root is on `sys.path`. The `pyproject.toml`'s test config already arranges this for `tests/`. For the production CLI, `codegenie.cli` will need to insert the repo root before invoking the loader — S6-04 owns that wire-up.
- CODEOWNERS placeholder: use `@platform-team` if the actual GitHub team handle is unknown at story-implementation time; leave a TODO in the commit message asking the human reviewer to substitute the correct handle. Do **not** invent a handle.
- The `_read_lock` helper accepts `{}` but should refuse to accept top-level non-objects (`[]`, scalars). Schema discipline applies to the lock file too.
- Reviewers will look for parity with `src/codegenie/probes/__init__.py`'s explicit-imports pattern. Comment the file's docstring with a brief "loader is the disk-walk counterpart; both reject `importlib.metadata` entry-point scans for the same supply-chain hygiene reason" so the asymmetry doesn't read as inconsistency.
- `LoadReport` (Pydantic, frozen) is the success payload. Keep it minimal: `loaded: list[PluginId]`, `total_walked: int`. Resist adding `timings: ...` etc. — that's bench-harness territory (S9-03).
