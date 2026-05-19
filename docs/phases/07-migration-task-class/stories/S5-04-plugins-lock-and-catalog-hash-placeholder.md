# Story S5-04 — `PLUGINS.lock` entry + Chainguard catalog hash-fence placeholder

**Step:** Step 5 — Phase 7 byte-edit allowlist fence + import-linter contracts + `PLUGINS.lock`
**Status:** Ready
**Effort:** S
**Depends on:** S5-01 (byte-edit allowlist fence is in place — `plugins/PLUGINS.lock` is allowlisted to receive additive rows by CODEOWNERS-gated review; the file itself is data, not code, so editing it is permitted under the existing Phase 3 lock-mechanism precedent).
**ADRs honored:** Phase 7 ADR-0009 (byte-edit allowlist — `plugins/PLUGINS.lock` is the data-attestation file Phase 3 established; row-by-row additions are within the existing CODEOWNERS mechanism); Phase 7 ADR-0010 (Chainguard CVE-image lookup is a frozen YAML — this story plants the file-hash fence placeholder that S9-02 finalizes); Phase 7 ADR-0005 (the plugin tree this lock row attests is `plugins/distroless-migration--node--npm/`); Phase 3 ADR-0011 (honest framing — `PLUGINS.lock` is integrity attestation, NOT cryptographic signature; CODEOWNERS is the social anchor; Sigstore is deferred to Phase 11).

## Context

`plugins/PLUGINS.lock` is the integrity-attestation file Phase 3 established (see `plugins/PLUGINS.lock.README.md`). It is a JSON object mapping each registered plugin's `PluginId` to the SHA-256 tree-digest of its directory under `plugins/`. The loader (`codegenie.plugins.loader.load_plugins`) refuses to import any plugin whose on-disk bytes do not match the digest attested here.

Phase 3 shipped `PLUGINS.lock` empty (`{}`) — the first concrete row was reserved for Phase 7. This story lands that first row: an entry for `distroless-migration--node--npm` mapping to `sha256(<plugin-tree>)`.

The companion artifact is the Chainguard CVE-to-image catalog hash fence. Phase 7 ADR-0010 mandates a frozen YAML at `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` whose file hash is pinned in a CI test. The final hash + file content land in S9-02; **this story plants the placeholder** so the fence file exists, the test infrastructure is wired, and S9-02 only has to swap the placeholder hash for the real one.

Why both at once: both artifacts are data-integrity fences with the same shape (CODEOWNERS-gated; file-hash-pinned; honest-framing as integrity-not-signature). Landing them together keeps the Step 5 "the mechanical fence layer" coherent.

**Honest framing (Phase 3 ADR-0011 carry-forward):** `PLUGINS.lock` and the catalog hash fence are integrity checks, not cryptographic signatures. They catch accidental corruption + partial-merge errors + unreviewed file changes. A determined adversary with write access defeats them trivially. CODEOWNERS at `.github/CODEOWNERS` gates legitimate edits; the PR template carries the regeneration checklist. Sigstore is deferred to Phase 11 — see `plugins/PLUGINS.lock.README.md` §"Honest framing".

## References — where to look

- **Phase ADRs:**
  - `../ADRs/0010-chainguard-cve-image-lookup-frozen-yaml.md` — the catalog YAML's location, schema, and hash-pinning policy.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — `plugins/PLUGINS.lock` is a data file outside the 10-row code allowlist; CODEOWNERS-gated edits follow the existing Phase 3 mechanism.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — the plugin tree this lock row attests.
- **Phase 3 precedent:**
  - `plugins/PLUGINS.lock.README.md` — read cover-to-cover. Names the regeneration helper `codegenie.plugins.loader.compute_plugin_tree_digest`, the CODEOWNERS gate, the deferred Sigstore migration. This story extends that file with a "Phase 7 — first concrete row landed" §.
  - `plugins/PLUGINS.lock` — currently `{}`. This story makes it `{"distroless-migration--node--npm": "sha256:<digest>"}`.
  - `Phase 3 ADR-0011` (honest framing) — the integrity-not-signature posture is inherited verbatim.
- **Architecture:**
  - `../phase-arch-design.md §Component design §(catalog)` — names the catalog YAML's location.
  - `../High-level-impl.md §Step 5` — names the `PLUGINS.lock` row as an exit-criteria item.
- **Existing code:**
  - `src/codegenie/plugins/loader.py::compute_plugin_tree_digest` — the deterministic SHA-256 of a plugin directory. Single source of truth; do not reimplement.
  - `src/codegenie/plugins/loader.py::load_plugins` — refuses to import plugins whose on-disk bytes don't match `PLUGINS.lock`. The runtime enforcer.
  - `tests/fence/test_phase3_importlinter_contracts_shape.py` — precedent for a fence-parsing test (parse a config file; assert structural invariants).
- **CODEOWNERS:**
  - `.github/CODEOWNERS` — `plugins/PLUGINS.lock` should already be covered by a rule like `plugins/PLUGINS.lock @<owners>` (verify; if not, this story adds the rule).

## Goal

Land the `distroless-migration--node--npm` row in `plugins/PLUGINS.lock` with the SHA-256 tree-digest of the plugin directory, and plant the `tests/fence/test_phase7_chainguard_lookup_table_loads.py` placeholder file (with a `pytest.mark.xfail(strict=True)` or skip-when-empty until S9-02 ships the real YAML). After this story, the loader can refuse to load the Phase 7 plugin when its on-disk bytes diverge from the attested digest, and S9-02 can swap the placeholder hash for the final value with minimal additional infrastructure work.

## Acceptance criteria

**`PLUGINS.lock` row addition (AC-1)**
- [ ] **AC-1** `plugins/PLUGINS.lock` is updated from `{}` to a JSON object with exactly one key — the plugin id `"distroless-migration--node--npm"` — mapped to the SHA-256 tree-digest of `plugins/distroless-migration--node--npm/` at story-landing time. The digest is in the form `"sha256:<64-hex-chars>"` (mirrors the existing `ImageDigest` smart-constructor convention from S1-01).
- [ ] **AC-1.a** The digest is computed via `codegenie.plugins.loader.compute_plugin_tree_digest(Path("plugins/distroless-migration--node--npm"))` — NOT a one-off `hashlib.sha256` call. Reusing the canonical function ensures the loader and the lockfile agree on the algorithm (file-tree walk order, hash-of-hashes shape, etc.).
- [ ] **AC-1.b** A unit test `tests/fence/test_phase7_plugin_lock_row_present.py` asserts (a) `PLUGINS.lock` parses as JSON, (b) the key `"distroless-migration--node--npm"` is present, (c) the value matches `^sha256:[0-9a-f]{64}$`. Drift fails CI.
- [ ] **AC-1.c** A second unit test asserts the digest in `PLUGINS.lock` matches the live `compute_plugin_tree_digest(...)` call against the on-disk plugin tree. This is the load-bearing integrity check — a future PR that edits a plugin file without regenerating `PLUGINS.lock` fails.

**Loader integration (AC-2)**
- [ ] **AC-2** `codegenie.plugins.loader.load_plugins()` succeeds on the Phase 7 plugin at story-landing time (the digest matches; the loader does not refuse). Verified by an integration test that calls `load_plugins()` and asserts the loaded report contains `distroless-migration--node--npm`.
- [ ] **AC-2.a** **Negative case:** a planted-tampering test (use `tmp_path` to copy the plugin tree, mutate one file's bytes, then point a test-only loader instance at the tmp copy with the original digest in a synthetic lock) asserts `load_plugins(...)` returns `Err` with a typed error naming the plugin id + "digest mismatch". This proves the lock is load-bearing at runtime, not just at lint time.

**`PLUGINS.lock.README.md` amendment (AC-3)**
- [ ] **AC-3** `plugins/PLUGINS.lock.README.md` is extended with a new section "Phase 7 — first concrete row" (or similar) that:
  - Names `distroless-migration--node--npm` as the first concrete plugin.
  - Names the regeneration command (already documented).
  - Cross-references Phase 7 ADR-0009 + Phase 3 ADR-0011 (honest framing).
  - Does NOT touch existing §s; one additive § append at the bottom.
- [ ] **AC-3.a** A meta-test scans the README for the literal strings `"distroless-migration--node--npm"` AND `"Phase 7"` AND `"sha256:"`.

**Chainguard catalog hash-fence placeholder (AC-4)**
- [ ] **AC-4** `tests/fence/test_phase7_chainguard_lookup_table_loads.py` exists with the following shape:
  - Module docstring cites Phase 7 ADR-0010 + Phase 3 ADR-0011 (honest framing).
  - `_CATALOG_PATH: Final[Path] = Path("plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml")`.
  - `_CATALOG_SHA256_PLACEHOLDER: Final[str] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"` — explicitly placeholder; an inline comment marks it as `# S9-02 will replace with the real hash`.
  - `test_catalog_file_exists`: `@pytest.mark.xfail(strict=True, reason="Catalog YAML lands in S9-01")` — passes-as-xfail at S5-04 landing; flips to pass at S9-01 landing.
  - `test_catalog_hash_matches_pinned`: computes `hashlib.sha256(<file-bytes>).hexdigest()` and asserts equality with `_CATALOG_SHA256_PLACEHOLDER[7:]` (strip the `sha256:` prefix). `@pytest.mark.xfail(strict=True, reason="Placeholder hash; S9-02 will pin the real value")` — passes-as-xfail at S5-04 landing.
- [ ] **AC-4.a** The placeholder file is wired into `make fence` / `make check` collection (collected transitively via `tests/fence/`). Verified by `pytest --collect-only tests/fence/test_phase7_chainguard_lookup_table_loads.py` reporting two collected items (both xfail-strict).
- [ ] **AC-4.b** **Hand-off documentation for S9-02:** module docstring contains a `## TODO(S9-02)` block listing exactly:
  1. Land `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` (S9-01).
  2. Compute the real SHA-256 of the file.
  3. Replace `_CATALOG_SHA256_PLACEHOLDER` with the real value.
  4. Remove both `xfail` markers.
  5. Verify the planted-violation matrix (mutate one byte; test goes red).
  - S9-02 implementer reads this and does exactly those five things.

**Planted-violation evidence (AC-5) — Rule 12 fail-loud**
- [ ] **AC-5** Out-of-test planted-violation evidence for the `PLUGINS.lock` row:
  - **AC-5.a** On a throwaway branch, mutate one file under `plugins/distroless-migration--node--npm/` (e.g., add a trailing newline to a `.py` file). Run `pytest tests/fence/test_phase7_plugin_lock_row_present.py` — AC-1.c fails with "digest mismatch". Record red SHA + output. Remove the mutation. Run again — green. Record green SHA. 3-line evidence block in `_attempts/S5-04.md`.
  - **AC-5.b** Confirm the runtime loader path: on the same throwaway branch (with the mutation re-applied), run `python -m codegenie gather <some-test-repo>` — the gather invokes `load_plugins`, which refuses the Phase 7 plugin with a typed error. Record the error output. This proves AC-2.a's runtime check is exercised end-to-end, not just by the unit test.
- [ ] **AC-5.c** For the Chainguard catalog placeholder: the xfail markers ARE the "fail-loud" mechanism at this stage. When S9-02 lands and removes the markers, S9-02's own planted-violation evidence (mutate one byte of the catalog YAML; test goes red) is the final demonstration. This story explicitly defers that proof to S9-02 and documents the hand-off in AC-4.b.

**CODEOWNERS coverage (AC-6)**
- [ ] **AC-6** `.github/CODEOWNERS` is verified to cover:
  - `plugins/PLUGINS.lock` (likely already covered by a `plugins/*.lock` rule — verify).
  - `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` (the placeholder file does not yet exist; the CODEOWNERS rule covers the path for when S9-01 lands it).
  - `tests/fence/test_phase7_chainguard_lookup_table_loads.py` (covered transitively via `tests/fence/`).
  - `tests/fence/test_phase7_plugin_lock_row_present.py` (covered transitively).
- [ ] **AC-6.a** If `plugins/PLUGINS.lock` is NOT already CODEOWNERS-covered, this story adds the rule. Otherwise: no edit.

**Cross-fence integration (AC-7)**
- [ ] **AC-7** `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` exits 0 — `plugins/PLUGINS.lock` is data and is NOT in the byte-edit allowlist (the allowlist is for code edits to existing Phase 0–6.5 *Python/JSON/TOML* files; `PLUGINS.lock` is the Phase 3 data-attestation file and is governed by CODEOWNERS, not by the byte-edit fence). Verify the fence's path-filter excludes `plugins/PLUGINS.lock` (or alternatively, that the lock-file edit is intentionally treated as in-scope and an 11th row is needed — coordinate with S5-01's path filter at implementation time). **Pin the decision at implementation time and document in `_attempts/S5-04.md`.**
- [ ] **AC-7.a** `make check` exits 0; no other fence regresses.

**Wiring (AC-8)**
- [ ] **AC-8** `ruff check`, `ruff format --check`, `mypy --strict` on touched test files clean. JSON formatting of `PLUGINS.lock` follows the existing convention (2-space indent; trailing newline; deterministic key order — only one key so order is trivial here).

## Implementation outline

1. **Confirm the plugin directory exists** at `plugins/distroless-migration--node--npm/` (lands in S4-02). If the directory does NOT exist yet at S5-04 implementation time, surface the dependency mismatch — S4-02 must precede S5-04 per the DAG.
2. **Compute the digest** — `python -c "from pathlib import Path; from codegenie.plugins.loader import compute_plugin_tree_digest; print(compute_plugin_tree_digest(Path('plugins/distroless-migration--node--npm')).unwrap())"`. Capture the value.
3. **Edit `plugins/PLUGINS.lock`** — change `{}` to `{"distroless-migration--node--npm": "sha256:<digest>"}` (use a JSON formatter that preserves the existing style).
4. **Write `tests/fence/test_phase7_plugin_lock_row_present.py`** with AC-1.b + AC-1.c + AC-2 + AC-2.a wiring.
5. **Append the new section to `plugins/PLUGINS.lock.README.md`** (AC-3).
6. **Write `tests/fence/test_phase7_chainguard_lookup_table_loads.py`** with AC-4's placeholder shape + the `## TODO(S9-02)` hand-off block (AC-4.b).
7. **Verify CODEOWNERS coverage** (AC-6); add rule if missing.
8. **Run `make check`** — green. Verify the byte-edit fence (S5-01) is not regressed (AC-7).
9. **Capture planted-violation evidence** (AC-5.a + AC-5.b) on a throwaway branch.

## TDD plan (red → green → refactor)

**Red:**
1. Write `tests/fence/test_phase7_plugin_lock_row_present.py` with all ACs but BEFORE editing `plugins/PLUGINS.lock`. Run `pytest tests/fence/test_phase7_plugin_lock_row_present.py` — AC-1.b fails (key not present), AC-1.c fails (digest mismatch — actually, the file is `{}` so the parse succeeds but the key-presence check fails first).
2. Edit `plugins/PLUGINS.lock` with a WRONG digest (e.g., all-zeros sha256). Run again — AC-1.b passes (key present), AC-1.c fails (mismatch). This proves the digest check is load-bearing.

**Green:**
1. Compute the real digest (step 2 of implementation outline). Edit `PLUGINS.lock` with the real value. Run — green.
2. Run the integration test (AC-2) — `load_plugins()` succeeds.
3. Run the planted-tampering test (AC-2.a) with `tmp_path` — the tampering case correctly returns `Err`.
4. Run `make check` — green.

**Refactor:**
1. Confirm `_CATALOG_SHA256_PLACEHOLDER`'s xfail markers are `strict=True` so a future accidental "remove markers without setting hash" lands as a failure.
2. Sort JSON keys deterministically in `PLUGINS.lock` (single key here; future-proofing for Phase 8+).
3. Confirm `ruff` / `mypy --strict` clean.

## Files to touch

- `plugins/PLUGINS.lock` — JSON edit `{}` → `{"distroless-migration--node--npm": "sha256:<digest>"}`.
- `plugins/PLUGINS.lock.README.md` — additive § appended at the bottom.
- `tests/fence/test_phase7_plugin_lock_row_present.py` — new test file.
- `tests/fence/test_phase7_chainguard_lookup_table_loads.py` — new placeholder test file (with `xfail(strict=True)` markers and `## TODO(S9-02)` hand-off block).
- `.github/CODEOWNERS` — verify; add rule for `plugins/PLUGINS.lock` if not already covered (likely already covered; surface in `_attempts/S5-04.md` if no edit needed).
- `_attempts/S5-04.md` — append-only attempt log with the AC-5.a + AC-5.b out-of-test planted-violation evidence + AC-7 path-filter decision documentation.

## Out of scope

- **The actual Chainguard catalog YAML content + its real SHA-256** — that's S9-01 (content) + S9-02 (hash pin). This story plants the placeholder + hand-off only.
- **Sigstore-bundled signed-artifact upgrade** — Phase 7 ADR-0010 + Phase 3 ADR-0011 defer to Phase 11.
- **Lock-file regeneration tooling (`codegenie plugins lock-update`)** — deferred to Phase 11 per `plugins/PLUGINS.lock.README.md` §"Regeneration". Manual regeneration via the documented Python one-liner is acceptable for Phase 7.
- **Phase 8+ plugin rows** — Phase 8 adds its row via its own story; this story plants only Phase 7's row.
- **Catalog-loader Pydantic schema** — S9-01's territory.

## Notes for the implementer

- **Honest framing is non-negotiable.** Read `plugins/PLUGINS.lock.README.md` §"Honest framing" before doing anything. The Sigstore migration deferral is named in Phase 3 ADR-0011 §Consequences; that ADR's framing carries forward to Phase 7 verbatim. Do NOT overstate what `PLUGINS.lock` provides; the README's wording is canonical.
- **Use `compute_plugin_tree_digest` — do not reimplement.** A one-off `hashlib.sha256(file_bytes)` call will diverge from the loader's tree-walk algorithm (the loader hashes files in a deterministic order, then hashes the concatenated digests). Reusing the canonical function guarantees agreement.
- **The xfail-strict markers are the load-bearing hand-off.** S9-02's job is to remove them and replace the placeholder hash. If S9-02 removes the markers WITHOUT setting the real hash, the test fails on every commit until fixed — that's the desired failure mode. `xfail(strict=True)` IS the safety net.
- **AC-7's path-filter decision needs a real answer at implementation time.** The S5-01 fence's `_LOCKED_SURFACE_GLOBS` does or does not include `plugins/PLUGINS.lock`. Read the S5-01 fence file; if the filter excludes the lock (as recommended), no allowlist change needed. If the filter includes it, this story needs to add an 11th row to ADR-0009 (NOT what we want) OR amend the S5-01 filter to exclude it (preferred, since the lock is data + CODEOWNERS-governed, not code). Pin the decision and document in `_attempts/S5-04.md`. **Surface the conflict explicitly per Rule 7 — do not silently average the two patterns.**
- **Anti-pattern explicitly avoided:** do NOT create a Pydantic schema for `PLUGINS.lock` in this story. The file is small (one key per plugin); JSON parsing + regex validation of the digest is sufficient (and matches the Phase 3 convention). Premature schema-isation violates Rule 2.
- **Coordinate with S9-01 / S9-02 implementers.** The `## TODO(S9-02)` block in `test_phase7_chainguard_lookup_table_loads.py` is the documentation hand-off, but a verbal/Slack hand-off is also helpful. Note in `_attempts/S5-04.md` that S9-02 inherits 5 mechanical steps.
- **CODEOWNERS social anchor.** The `.github/CODEOWNERS` rule for `plugins/PLUGINS.lock` is what makes this an integrity attestation (legitimate edits require CODEOWNERS sign-off; accidents / unreviewed edits do not get past review). Verify the rule covers the file; if it does not, this is the moment to add it — surface in `_attempts/S5-04.md`.
- **Performance:** `compute_plugin_tree_digest` is O(plugin-tree-size); the Phase 7 plugin is small (~10 files at S5-04 landing). Negligible cost. No perf budget concern.
