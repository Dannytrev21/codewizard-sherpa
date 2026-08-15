# Story S5-04 — `PLUGINS.lock` entry + Chainguard catalog hash-fence placeholder

**Step:** Step 5 — Phase 7 byte-edit allowlist fence + import-linter contracts + `PLUGINS.lock`
**Status:** HARDENED (phase-story-validator, 2026-08-14; see `_validation/S5-04-plugins-lock-and-catalog-hash-placeholder.md`)
**Effort:** S
**Depends on:**
- **S5-01** (Phase 7 byte-edit allowlist fence — HARDENED 2026-08-14. `AC-4.a` of that story explicitly EXCLUDES `plugins/PLUGINS.lock` from `_LOCKED_SURFACE_GLOBS`, delegating ownership of the exclusion to S5-04. S5-04 verifies that exclusion is intact — AC-7.)
- **S4-02** (`AlpineVulnProvenanceAdapter` — creates `plugins/distroless-migration--node--npm/` directory + `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py`).
- **S4-03** (`DistrolessVulnProvenanceAdapter` — adds the distroless adapter + `plugins/distroless-migration--node--npm/api.py`). Both must land before S5-04 opens so the plugin tree exists to be digested.

**ADRs honored:** Phase 7 ADR-0009 (byte-edit allowlist — `plugins/PLUGINS.lock` is *data* attestation and lies outside the *code* allowlist; row-by-row additions are governed by the CODEOWNERS mechanism); Phase 7 ADR-0010 (Chainguard CVE-image lookup is a frozen YAML — this story plants the file-hash fence placeholder that S9-02 finalises); Phase 7 ADR-0005 (the plugin tree this lock row attests is `plugins/distroless-migration--node--npm/`); Phase 3 ADR-0011 (honest framing — `PLUGINS.lock` is integrity attestation, NOT cryptographic signature; CODEOWNERS is the social anchor; Sigstore is deferred to Phase 11).

## Validation notes (phase-story-validator, 2026-08-14)

Hardened by the four-critic phase-story-validator pipeline; full audit in `_validation/S5-04-plugins-lock-and-catalog-hash-placeholder.md`. Summary of edits:

1. **Blocker — digest format contradicted `BlobDigest`.** The original draft required every `PLUGINS.lock` value in the form `"sha256:<64-hex>"` (AC-1 + AC-1.b regex `^sha256:[0-9a-f]{64}$`). `src/codegenie/types/parsers.py::parse_blob_digest` rejects anything other than 64 lowercase hex chars; `LockFile` (`RootModel[dict[PluginId, BlobDigest]]`) would return `Err(LockFileMalformed)` on a `"sha256:…"` value, breaking `load_plugins()` for the *existing* plugin too. All digest-value shape + regex references corrected to raw 64-hex.
2. **Blocker — "PLUGINS.lock ships empty" claim was stale.** Phase-3 S7-01 already landed the first concrete row (`vulnerability-remediation--node--npm`). This story lands the **second** row (first Phase-7 row). Context, Goal, AC-1 rewritten to reflect the second-row reality.
3. **Blocker — AC-7 asked the implementer to "pin the decision at implementation time".** S5-01's HARDENED validation (2026-08-14) already pinned it: `plugins/PLUGINS.lock` is EXCLUDED from `_LOCKED_SURFACE_GLOBS`. AC-7 rewritten as a **verification** of that exclusion rather than an open question.
4. **AC-2 hardening (cross-plugin regression):** `load_plugins()` must succeed for BOTH plugins after the edit and the `LoadReport` must enumerate both plugin ids. Prevents a swap-mistake from silently breaking the pre-existing plugin.
5. **AC-2.a hardening (typed-error precision):** Assert on `IntegrityMismatch(kind="integrity_mismatch", plugin=<id>)` structural fields, not on a free-text "digest mismatch" string. Mutation-resistant.
6. **AC-1.c hardening (typed compare):** Compare `BlobDigest` newtype values, not raw strings, so `mypy --strict` catches an accidental string substitution.
7. **AC-4.a hardening (xfail-strict integrity):** Assert that BOTH catalog-test items are collected AND both are marked `xfail(strict=True)`; catches a future refactor that quietly drops `strict=True`.
8. **AC-3 addition (README stale-wording correction):** Also fix the "Phase 3 ships empty" stale wording in `plugins/PLUGINS.lock.README.md`.
9. **AC-6 tightening (CODEOWNERS):** Grep for the exact rule string `plugins/PLUGINS.lock @Dannytrev21` — the file is already covered; AC-6.a will report "no edit needed".
10. **`_HASH_PREFIX_INTENT` sentinel:** The catalog placeholder deliberately uses `"sha256:"` prefix (single-file file-hash vs. `BlobDigest` tree-digest — the visual distinction is intentional). Documented via a module-level `_HASH_PREFIX_INTENT: Final[str] = "sha256:"` with rationale docstring.
11. **Notes-for-implementer:** Removed "pin the decision" open-question language; added explicit "do NOT introduce a `@register_catalog_hash_pin` registry" and "do NOT modify `PluginVerifier`" anti-abstraction guardrails per Rule 2 + the already-hexagonal Sigstore seam.

**Verdict:** HARDENED — no structural rescue needed. Three surface blockers (all traceable to writing against Phase-3-past state) fully corrected. Ready for phase-story-executor.

## Context

`plugins/PLUGINS.lock` is the integrity-attestation file Phase 3 established (see `plugins/PLUGINS.lock.README.md`). It is a JSON object mapping each registered plugin's `PluginId` to the SHA-256 tree-digest of its directory under `plugins/`. The loader (`codegenie.plugins.loader.load_plugins`) refuses to import any plugin whose on-disk bytes do not match the digest attested here.

**Current on-disk state (verified at story-hardening time, 2026-08-14):** `PLUGINS.lock` contains **one** row — `{"vulnerability-remediation--node--npm": "<64-hex tree-digest>"}` — landed by Phase-3 S7-01. This story lands the **second** concrete row (first Phase-7 row): an entry for `distroless-migration--node--npm` mapping to the raw 64-lowercase-hex SHA-256 tree-digest of `plugins/distroless-migration--node--npm/`.

**Digest format is raw 64-lowercase-hex, no prefix.** This is dictated by `src/codegenie/types/parsers.py::parse_blob_digest` (regex `^[0-9a-f]{64}$`), by `LockFile` (`RootModel[dict[PluginId, BlobDigest]]`), and by `Sha256TreeDigestVerifier`. A `"sha256:…"` value causes `LockFile.from_path` to return `Err(LockFileMalformed)`, which `load_plugins` propagates — breaking BOTH plugins. **Do not add a `sha256:` prefix to any `PLUGINS.lock` value.**

The companion artifact is the Chainguard CVE-to-image catalog hash fence. Phase 7 ADR-0010 mandates a frozen YAML at `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` whose file hash is pinned in a CI test. The final hash + file content land in S9-02; **this story plants the placeholder** so the fence file exists, the test infrastructure is wired, and S9-02 only has to swap the placeholder hash for the real one. The catalog hash is a **single-file file-hash**, distinct in purpose from `BlobDigest` (which is a plugin *tree*-digest); the placeholder deliberately uses a `"sha256:"` prefix to mark it as a different kind of hash (see AC-4 + `_HASH_PREFIX_INTENT`).

Why both at once: both artifacts are data-integrity fences with a similar operator-facing shape (CODEOWNERS-gated; file-hash-pinned; honest-framing as integrity-not-signature). Landing them together keeps the Step 5 "the mechanical fence layer" coherent.

**Honest framing (Phase 3 ADR-0011 carry-forward):** `PLUGINS.lock` and the catalog hash fence are integrity checks, not cryptographic signatures. They catch accidental corruption + partial-merge errors + unreviewed file changes. A determined adversary with write access defeats them trivially. CODEOWNERS at `.github/CODEOWNERS` gates legitimate edits (verified: `plugins/PLUGINS.lock @Dannytrev21` is already present); the PR template carries the regeneration checklist. Sigstore is deferred to Phase 11 — see `plugins/PLUGINS.lock.README.md` §"Honest framing".

## References — where to look

- **Phase ADRs:**
  - `../ADRs/0010-chainguard-cve-image-lookup-frozen-yaml.md` — the catalog YAML's location, schema, and hash-pinning policy.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — `plugins/PLUGINS.lock` is a data file outside the 10-row code allowlist; CODEOWNERS-gated edits follow the existing Phase 3 mechanism.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — the plugin tree this lock row attests.
- **Phase 3 precedent:**
  - `plugins/PLUGINS.lock.README.md` — read cover-to-cover. Names the regeneration helper `codegenie.plugins.loader.compute_plugin_tree_digest`, the CODEOWNERS gate, the deferred Sigstore migration. This story corrects the stale "Phase 3 state — empty" § in place (per AC-3(a)) and appends a new "Phase 7 — distroless migration row" § (per AC-3(b)).
  - `plugins/PLUGINS.lock` — currently one row (`{"vulnerability-remediation--node--npm": "<64-hex>"}` — landed by Phase-3 S7-01). This story adds an **additive** second key so the file becomes `{"distroless-migration--node--npm": "<64-hex>", "vulnerability-remediation--node--npm": "<existing-64-hex>"}` (lexicographically sorted; raw 64-hex values, no `sha256:` prefix).
  - **Phase 3 S7-01** — the first-row precedent this story follows exactly (same digest format, same regeneration workflow, same CODEOWNERS gate).
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

Land a **second** row in `plugins/PLUGINS.lock` (the first was Phase-3 S7-01's `vulnerability-remediation--node--npm`; this story adds `distroless-migration--node--npm`) with the raw-64-hex SHA-256 tree-digest of the plugin directory, and plant the `tests/fence/test_phase7_chainguard_lookup_table_loads.py` placeholder file (`pytest.mark.xfail(strict=True)` on both catalog tests until S9-02 ships the real YAML + real hash). After this story: (a) the loader can refuse to import the Phase-7 plugin when its on-disk bytes diverge from the attested digest, (b) the pre-existing Phase-3 plugin still loads cleanly (cross-plugin regression check is load-bearing), and (c) S9-02 can swap the placeholder hash for the final value with a five-step mechanical patch (documented in AC-4.b).

## Acceptance criteria

**`PLUGINS.lock` row addition (AC-1)**
- [ ] **AC-1** `plugins/PLUGINS.lock` is updated by adding one **additive** key `"distroless-migration--node--npm"` — mapped to the SHA-256 tree-digest of `plugins/distroless-migration--node--npm/` at story-landing time. The digest is stored as **raw 64 lowercase hex characters, no `sha256:` prefix** (matches the existing `vulnerability-remediation--node--npm` row shape and the `BlobDigest` newtype accepted by `parse_blob_digest`). The pre-existing `vulnerability-remediation--node--npm` row MUST be preserved byte-identical.
- [ ] **AC-1.a** The digest is computed via `codegenie.plugins.loader.compute_plugin_tree_digest(Path("plugins/distroless-migration--node--npm"))` — NOT a one-off `hashlib.sha256` call. Reusing the canonical function ensures the loader and the lockfile agree on the algorithm (file-tree walk order, hash-of-hashes shape, etc.). Call `.unwrap()` at the CLI capture site only; production tests use `isinstance(result, Ok)`.
- [ ] **AC-1.b** A unit test `tests/fence/test_phase7_plugin_lock_row_present.py` asserts (a) `PLUGINS.lock` parses as JSON (`json.loads(path.read_text())`), (b) the key `"distroless-migration--node--npm"` is present, (c) the value matches the regex `^[0-9a-f]{64}$` (mirrors `_HEX64_PATTERN` in `src/codegenie/types/parsers.py` — NOT `^sha256:[0-9a-f]{64}$`; adding a `sha256:` prefix would fail `parse_blob_digest` and break `LockFile.from_path`), (d) the pre-existing `vulnerability-remediation--node--npm` key is still present with a value matching the same regex. Drift on either row fails CI.
- [ ] **AC-1.c** A second unit test asserts the digest recorded in `PLUGINS.lock` for `distroless-migration--node--npm` equals the live `compute_plugin_tree_digest(Path("plugins/distroless-migration--node--npm")).unwrap()` result. Assertion compares `BlobDigest` newtype values directly (`assert lock_digest == live_digest` where both are typed `BlobDigest`) so `mypy --strict` catches a future accidental string substitution. This is the load-bearing runtime integrity check — a future PR that edits a plugin file without regenerating `PLUGINS.lock` fails.
- [ ] **AC-1.d** A third unit test asserts `LockFile.from_path(Path("plugins/PLUGINS.lock"))` returns `Ok(LockFile)` (not `Err(LockFileMalformed)`). This exercises the full Pydantic parse path — a stronger check than raw `json.loads` because it also fails if any digest violates the `BlobDigest` shape.

**Loader integration (AC-2)**
- [ ] **AC-2** `codegenie.plugins.loader.load_plugins(plugin_root=Path("plugins"), lock_path=Path("plugins/PLUGINS.lock"))` returns `Ok(LoadReport)` at story-landing time, and the `LoadReport.loaded` tuple contains **both** plugin ids as `PluginId` values: `PluginId("vulnerability-remediation--node--npm")` AND `PluginId("distroless-migration--node--npm")`. Assertion is by set-equality on the `plugin_id` field, not by count-only — a bug that swaps one for the other fails.
- [ ] **AC-2.a** **Negative case (planted tampering):** Copy the Phase-7 plugin tree into `tmp_path`, mutate one file's bytes (e.g., append a trailing newline to a `.py` file), synthesise a lock file that pairs the tampered directory with its *original* (pre-mutation) digest, then call `load_plugins(plugin_root=tmp_path, lock_path=<synth-lock>)`. Assert the result is `Err(IntegrityMismatch)` where `err.kind == "integrity_mismatch"` AND `err.plugin == PluginId("distroless-migration--node--npm")` AND `err.expected != err.actual`. Assertion is on the structural typed error, not on a message-string substring — mutation-resistant against future error-text rewording. This proves the lock is load-bearing at runtime, not just at lint time.

**`PLUGINS.lock.README.md` amendment (AC-3)**
- [ ] **AC-3** `plugins/PLUGINS.lock.README.md` is amended in two ways:
  - (a) The stale "Phase 3 state — empty" section is corrected in place to reflect the actual current state: shipped empty in Phase 3, first concrete row landed by Phase-3 S7-01 (`vulnerability-remediation--node--npm`), second row landed by Phase-7 S5-04 (`distroless-migration--node--npm`). Rename the section "Concrete rows landed" (or similar); keep it two short paragraphs; do not touch other §s.
  - (b) A new section "Phase 7 — distroless migration row" is appended at the bottom that:
    - Names `distroless-migration--node--npm` as the Phase-7 plugin.
    - Names the regeneration command (already documented in §Regeneration).
    - Cross-references Phase 7 ADR-0009 (byte-edit allowlist context) + Phase 7 ADR-0010 (Chainguard catalog) + Phase 3 ADR-0011 (honest framing).
    - Reminds readers digests are raw 64-hex (no `sha256:` prefix).
- [ ] **AC-3.a** A meta-test scans the README for the literal strings `"distroless-migration--node--npm"` AND `"Phase 7"` AND `"vulnerability-remediation--node--npm"` (confirms the historical wording was corrected, not just appended to).

**Chainguard catalog hash-fence placeholder (AC-4)**
- [ ] **AC-4** `tests/fence/test_phase7_chainguard_lookup_table_loads.py` exists with the following shape:
  - Module docstring cites Phase 7 ADR-0010 + Phase 3 ADR-0011 (honest framing) + explains that this catalog hash is a **single-file file-hash**, DELIBERATELY prefixed with `sha256:` to make it visually distinct from `BlobDigest` (which is a plugin *tree*-digest and stored raw-hex without prefix). This is documented via a module-level sentinel:
    ```python
    # The "sha256:" prefix on _CATALOG_SHA256_PLACEHOLDER is deliberate — it marks
    # this hash as a single-file file-hash, distinct from BlobDigest (plugin tree
    # digest, raw 64-hex, no prefix). Do not "normalise" to raw hex; the visual
    # distinction is a maintenance affordance.
    _HASH_PREFIX_INTENT: Final[str] = "sha256:"
    ```
  - `_CATALOG_PATH: Final[Path] = Path("plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml")`.
  - `_CATALOG_SHA256_PLACEHOLDER: Final[str] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"` — explicitly placeholder; an inline comment marks it as `# S9-02 will replace with the real hash`.
  - `test_catalog_file_exists`: `@pytest.mark.xfail(strict=True, reason="Catalog YAML lands in S9-01")` — the test asserts `_CATALOG_PATH.exists()` and is expected to fail at S5-04 landing. When S9-01 lands the YAML, this test will `XPASS`, and `strict=True` flips `XPASS` to failure — forcing S9-01 to remove the marker in the same commit.
  - `test_catalog_hash_matches_pinned`: computes `hashlib.sha256(_CATALOG_PATH.read_bytes()).hexdigest()` and asserts equality with `_CATALOG_SHA256_PLACEHOLDER.removeprefix(_HASH_PREFIX_INTENT)` (strip the prefix). `@pytest.mark.xfail(strict=True, reason="Placeholder hash; S9-02 will pin the real value")` — expected to fail at S5-04 landing (file absent → `FileNotFoundError`; strict-xfail treats any failure as expected).
- [ ] **AC-4.a** The placeholder file is wired into `make fence` / `make check` collection (collected transitively via `tests/fence/`). Verified by a meta-test that:
  1. Uses `pytest --collect-only tests/fence/test_phase7_chainguard_lookup_table_loads.py` (or the equivalent `_pytest.config` API) to collect the module.
  2. Asserts **exactly two** items are collected.
  3. For **each** collected item, inspects `item.get_closest_marker("xfail")` and asserts (a) the marker is present, AND (b) `marker.kwargs.get("strict") is True`. A future refactor that drops `strict=True` on *either* test fails this AC — closes the "silently downgraded xfail" gap.
- [ ] **AC-4.b** **Hand-off documentation for S9-02:** module docstring contains a `## TODO(S9-02)` block listing exactly:
  1. Land `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` (S9-01).
  2. Compute the real SHA-256 of the file (`hashlib.sha256(path.read_bytes()).hexdigest()`).
  3. Replace `_CATALOG_SHA256_PLACEHOLDER` with `f"sha256:{<real-hex>}"` (keep the prefix — see `_HASH_PREFIX_INTENT`).
  4. Remove both `xfail` markers.
  5. Verify the planted-violation matrix (mutate one byte of the catalog YAML; both tests go red on the next `make check`).
  - S9-02 implementer reads this and does exactly those five things.

**Planted-violation evidence (AC-5) — Rule 12 fail-loud**
- [ ] **AC-5** Out-of-test planted-violation evidence for the `PLUGINS.lock` row:
  - **AC-5.a** On a throwaway branch, mutate one file under `plugins/distroless-migration--node--npm/` (e.g., append a trailing newline to a `.py` file). Run `pytest tests/fence/test_phase7_plugin_lock_row_present.py -v` — AC-1.c fails with an `AssertionError` where the mismatch is between the lock's recorded `BlobDigest` and the newly-computed live digest. Record red SHA + failure output. Remove the mutation. Run again — green. Record green SHA. 3-line evidence block in `_attempts/S5-04.md`.
  - **AC-5.b** Confirm the runtime loader path: on the same throwaway branch (with the mutation re-applied), run `python -c "from pathlib import Path; from codegenie.plugins.loader import load_plugins; r = load_plugins(Path('plugins'), Path('plugins/PLUGINS.lock')); print(r)"` — the result is `Err(IntegrityMismatch(kind='integrity_mismatch', plugin=PluginId('distroless-migration--node--npm'), expected=..., actual=...))`. Record the printed error. This proves AC-2.a's runtime check is exercised end-to-end via the real loader against real disk, not just the unit-test synthetic-tmp path.
  - **AC-5.b.i** Additionally, on the same throwaway branch (mutation still applied), assert the loader-registry invariant holds: after the `Err` return, `codegenie.plugins.registry.default_registry.all() == ()` — verify-all-then-import-all was honored and the first plugin's module was not partially registered. One-line evidence.
- [ ] **AC-5.c** For the Chainguard catalog placeholder: the xfail markers ARE the "fail-loud" mechanism at this stage. When S9-02 lands and removes the markers, S9-02's own planted-violation evidence (mutate one byte of the catalog YAML; test goes red) is the final demonstration. This story explicitly defers that proof to S9-02 and documents the hand-off in AC-4.b.

**CODEOWNERS coverage (AC-6)**
- [ ] **AC-6** `.github/CODEOWNERS` is verified — at story-hardening time (2026-08-14), grep confirms the line `plugins/PLUGINS.lock @Dannytrev21` is already present. AC-6 is a **verification** AC (asserts the line still exists) not an "add-if-missing" AC.
- [ ] **AC-6.a** `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` will not exist at S5-04 landing (arrives in S9-01). No CODEOWNERS entry is required at S5-04 landing time — S9-01 is responsible for adding the rule when it lands the file (surface in S9-01's story, not S5-04's scope).
- [ ] **AC-6.b** Both new fence test files land under `tests/fence/` (already covered transitively via any existing `tests/fence/ @…` rule if present; otherwise both files inherit repo-root CODEOWNERS by default — verify at implementation time via `grep -E "^tests/fence" .github/CODEOWNERS`).

**Cross-fence integration (AC-7)**
- [ ] **AC-7** `plugins/PLUGINS.lock` is EXCLUDED from `_LOCKED_SURFACE_GLOBS` in `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` — this decision was pinned by S5-01 AC-4.a (HARDENED 2026-08-14) and S5-04 is its verifier, not its decider. Assert the exclusion by importing `_LOCKED_SURFACE_GLOBS` and running `import fnmatch; assert not any(fnmatch.fnmatchcase("plugins/PLUGINS.lock", g) for g in _LOCKED_SURFACE_GLOBS)`. If this assertion fails, the S5-01 fence has silently drifted — **stop and coordinate with the S5-01 owner rather than adding an 11th row** (per Rule 7 + ADR-0009's "no silent row growth" invariant; growth must go through a per-row ADR amendment).
- [ ] **AC-7.a** `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` exits 0 on the branch that carries the `PLUGINS.lock` row edit — proves the exclusion is functional end-to-end, not just declaratively present.
- [ ] **AC-7.b** `make check` exits 0; no other fence regresses (`test_phase7_no_llm.py`, `test_phase7_importlinter_contracts_shape.py`, `test_lint_imports_catches_phase7_planted_leak.py`, `test_openrewrite_phase7_markers.py` all still green).

**Wiring (AC-8)**
- [ ] **AC-8** `ruff check`, `ruff format --check`, `mypy --strict` on touched test files clean. JSON formatting of `PLUGINS.lock` follows the existing convention (single-line JSON object, no trailing newline drift — grep the existing file for the current style and match exactly). Deterministic key order: keys sorted lexicographically (`json.dumps(..., sort_keys=True)` when regenerating), so PR diffs are stable.

## Implementation outline

1. **Confirm the plugin directory exists** at `plugins/distroless-migration--node--npm/` — populated by Phase-7 S4-02 (`alpine_provenance.py`) + S4-03 (`distroless_provenance.py` + `api.py`). If the directory does NOT exist yet at S5-04 implementation time, surface the dependency mismatch — S4-02 + S4-03 must precede S5-04 per the DAG.
2. **Confirm the current `PLUGINS.lock` state** — `cat plugins/PLUGINS.lock` should show exactly the pre-existing `vulnerability-remediation--node--npm` row with a raw-64-hex value. If any other state is observed (empty, prefix drift, multi-row), stop and reconcile before proceeding.
3. **Compute the new digest** — `python -c "from pathlib import Path; from codegenie.plugins.loader import compute_plugin_tree_digest; print(compute_plugin_tree_digest(Path('plugins/distroless-migration--node--npm')).unwrap())"`. Capture the raw-64-hex value (no `sha256:` prefix).
4. **Edit `plugins/PLUGINS.lock`** — add the additive key so the file becomes `{"distroless-migration--node--npm": "<64-hex>", "vulnerability-remediation--node--npm": "<existing-64-hex>"}` (keys sorted lexicographically per AC-8). Do NOT touch the pre-existing digest.
5. **Write `tests/fence/test_phase7_plugin_lock_row_present.py`** with AC-1.b + AC-1.c + AC-1.d + AC-2 + AC-2.a wiring.
6. **Amend `plugins/PLUGINS.lock.README.md`** — correct the stale "Phase 3 state — empty" section in place per AC-3(a) and append the new "Phase 7 — distroless migration row" section per AC-3(b).
7. **Write `tests/fence/test_phase7_chainguard_lookup_table_loads.py`** with AC-4's placeholder shape + `_HASH_PREFIX_INTENT` sentinel + the `## TODO(S9-02)` hand-off block (AC-4.b) + the AC-4.a xfail-strict meta-test.
8. **Verify CODEOWNERS coverage** (AC-6) — grep confirms `plugins/PLUGINS.lock @Dannytrev21` is present; no edit needed.
9. **Assert the S5-01 exclusion** (AC-7) — import `_LOCKED_SURFACE_GLOBS` from the S5-01 fence module and prove `plugins/PLUGINS.lock` is not matched. If it IS matched, stop and coordinate with S5-01 owner.
10. **Run `make check`** — green. Verify the byte-edit fence (S5-01) is not regressed (AC-7.a + AC-7.b).
11. **Capture planted-violation evidence** (AC-5.a + AC-5.b + AC-5.b.i) on a throwaway branch.

## TDD plan (red → green → refactor)

**Red:**
1. Write `tests/fence/test_phase7_plugin_lock_row_present.py` with AC-1.b + AC-1.c + AC-1.d + AC-2 BEFORE editing `plugins/PLUGINS.lock`. Run `pytest tests/fence/test_phase7_plugin_lock_row_present.py -v` —
   - AC-1.b fails (key `distroless-migration--node--npm` not present in the current one-row lock).
   - AC-1.d passes trivially (the current lock already parses via `LockFile.from_path`).
   - AC-2 fails (`load_plugins()` returns `Ok(LoadReport)` with only ONE plugin id, missing `distroless-migration--node--npm` — the set-equality assertion fails).
2. Edit `plugins/PLUGINS.lock` — add the new key with a WRONG digest (e.g., all-zeros 64-hex `"0" * 64`). Run again —
   - AC-1.b passes (key present, regex matches).
   - AC-1.c fails (`BlobDigest` mismatch: expected all-zeros, actual live digest).
   - AC-1.d passes (all-zeros is valid `BlobDigest` shape).
   - AC-2 fails (`load_plugins()` returns `Err(IntegrityMismatch)`).
   - This proves the digest check is load-bearing on the real file, not just synthetic tests.
3. Write `tests/fence/test_phase7_chainguard_lookup_table_loads.py` with AC-4's shape + AC-4.a meta-test. Run — both catalog tests XFAIL as expected; AC-4.a meta-test PASSES (both items collected AND marked strict-xfail).

**Green:**
1. Compute the real digest (step 3 of implementation outline). Edit `PLUGINS.lock` to replace the placeholder digest with the real value. Run — all ACs green.
2. Run the integration test (AC-2) — `load_plugins()` returns `Ok(LoadReport)` with both plugin ids in `loaded`.
3. Run the planted-tampering test (AC-2.a) — the tampering case correctly returns `Err(IntegrityMismatch)` with the expected `plugin` field.
4. Run `make check` — green.

**Refactor:**
1. Confirm both `_CATALOG_SHA256_PLACEHOLDER` xfail markers are `strict=True` (AC-4.a meta-test enforces this at runtime; grep the file as belt-and-braces).
2. Confirm `plugins/PLUGINS.lock` keys are lexicographically sorted (AC-8; regenerate via `json.dumps(..., sort_keys=True)` if drift).
3. Confirm `ruff check`, `ruff format --check`, `mypy --strict` all clean on the touched test files.
4. Confirm the `## Validation notes` block on this story records any additional discoveries made during implementation (a discovery that a critic missed is signal — surface via an `_attempts/S5-04.md` "lessons" line).

## Files to touch

- `plugins/PLUGINS.lock` — JSON edit adding the additive key `distroless-migration--node--npm` (raw 64-hex value, no `sha256:` prefix). Keys sorted lexicographically. Pre-existing `vulnerability-remediation--node--npm` row preserved byte-identical.
- `plugins/PLUGINS.lock.README.md` — in-place correction of the stale "Phase 3 state — empty" § (AC-3(a)) + additive "Phase 7 — distroless migration row" § at the bottom (AC-3(b)).
- `tests/fence/test_phase7_plugin_lock_row_present.py` — new test file covering AC-1.b, AC-1.c, AC-1.d, AC-2, AC-2.a.
- `tests/fence/test_phase7_chainguard_lookup_table_loads.py` — new placeholder test file (with `_HASH_PREFIX_INTENT` sentinel, `xfail(strict=True)` markers, `## TODO(S9-02)` hand-off block, and the AC-4.a meta-test for xfail-strict integrity).
- `.github/CODEOWNERS` — no edit; verify `plugins/PLUGINS.lock @Dannytrev21` is present.
- `_attempts/S5-04.md` — append-only attempt log with AC-5.a + AC-5.b + AC-5.b.i out-of-test planted-violation evidence + AC-7 verification result (S5-01 exclusion intact) + any implementation-time discoveries that the validator missed.

## Out of scope

- **The actual Chainguard catalog YAML content + its real SHA-256** — that's S9-01 (content) + S9-02 (hash pin). This story plants the placeholder + hand-off only.
- **Sigstore-bundled signed-artifact upgrade** — Phase 7 ADR-0010 + Phase 3 ADR-0011 defer to Phase 11.
- **Lock-file regeneration tooling (`codegenie plugins lock-update`)** — deferred to Phase 11 per `plugins/PLUGINS.lock.README.md` §"Regeneration". Manual regeneration via the documented Python one-liner is acceptable for Phase 7.
- **Phase 8+ plugin rows** — Phase 8 adds its row via its own story; this story plants only Phase 7's row.
- **Catalog-loader Pydantic schema** — S9-01's territory.

## Notes for the implementer

- **Digest format is raw 64-lowercase-hex — no `sha256:` prefix on any value in `PLUGINS.lock`.** This is dictated by `parse_blob_digest` + the `BlobDigest` newtype + `LockFile`. Adding a prefix causes `LockFile.from_path` to return `Err(LockFileMalformed)`, breaking `load_plugins()` for BOTH plugins. The pre-existing `vulnerability-remediation--node--npm` row is the format oracle — mirror its shape byte-for-byte. **The `sha256:` prefix ONLY appears in the catalog-hash placeholder `_CATALOG_SHA256_PLACEHOLDER`, deliberately, to mark it as a *different* kind of hash (single-file file-hash, not plugin tree-digest).**
- **Honest framing is non-negotiable.** Read `plugins/PLUGINS.lock.README.md` §"Honest framing" before doing anything. The Sigstore migration deferral is named in Phase 3 ADR-0011 §Consequences; that ADR's framing carries forward to Phase 7 verbatim. Do NOT overstate what `PLUGINS.lock` provides; the README's wording is canonical.
- **Use `compute_plugin_tree_digest` — do not reimplement.** A one-off `hashlib.sha256(file_bytes)` call will diverge from the loader's tree-walk algorithm (the loader hashes files in a deterministic order via `_collect_plugin_files` → `tree_digest_of_files`, then lifts through `parse_blob_digest` to produce a `BlobDigest`). Reusing the canonical function guarantees agreement.
- **The xfail-strict markers are the load-bearing hand-off.** S9-02's job is to remove them and replace the placeholder hash. If S9-02 removes the markers WITHOUT setting the real hash, the test fails on every commit until fixed — that's the desired failure mode. `xfail(strict=True)` IS the safety net. AC-4.a's meta-test enforces this at runtime — a future refactor cannot silently downgrade `strict=True` without failing.
- **AC-7 is a verification, not a decision.** S5-01 AC-4.a (HARDENED 2026-08-14) already pinned `plugins/PLUGINS.lock`'s exclusion from `_LOCKED_SURFACE_GLOBS`. S5-04 asserts the exclusion is intact. If the assertion fails, the S5-01 fence has drifted — **stop and coordinate with the S5-01 owner rather than adding an 11th row to ADR-0009's allowlist** (per Rule 7 + ADR-0009's "no silent row growth" invariant; growth must go through a per-row ADR amendment).
- **Anti-pattern explicitly avoided — no premature abstraction:**
  - Do NOT create a Pydantic schema for `PLUGINS.lock` in this story. The `LockFile` `RootModel` in `src/codegenie/plugins/lockfile.py` already exists; using it via `LockFile.from_path` (AC-1.d) is the sanctioned entry point.
  - Do NOT introduce a `@register_catalog_hash_pin` registry for the Chainguard catalog. There is only one catalog file today. Rule of three is not met (Rule 2). If a third similar single-file hash-pin ever lands, THAT is the moment to extract a registry — with the two existing pins as evidence of a recurring pattern, not speculation.
  - Do NOT modify `PluginVerifier` or `Sha256TreeDigestVerifier`. The Sigstore substitution seam is already hexagonal (Phase 11 swaps `SigstoreVerifier` in at the `PluginVerifier` Protocol with zero loader changes).
- **The `BlobDigest` newtype must appear in typed compares.** AC-1.c's assertion `assert lock_digest == live_digest` — both sides typed `BlobDigest` — is not cosmetic. It's the load-bearing signal to `mypy --strict` that a future accidental `str` substitution (e.g., someone reading the file via `json.loads` without going through `LockFile.from_path`) will be caught at type-check time, not at runtime with a confusing "why does this string equal that string" bug.
- **Coordinate with S9-01 / S9-02 implementers.** The `## TODO(S9-02)` block in `test_phase7_chainguard_lookup_table_loads.py` is the primary documentation hand-off. Note in `_attempts/S5-04.md` that S9-02 inherits exactly 5 mechanical steps (spelled out in AC-4.b).
- **CODEOWNERS social anchor is already in place.** `.github/CODEOWNERS` already contains `plugins/PLUGINS.lock @Dannytrev21` (verified at story-hardening time, 2026-08-14). AC-6 is a verification, not an add-if-missing.
- **README stale-wording correction (AC-3(a)):** The current README says "The lock ships empty (`{}`) in Phase 3. The first concrete plugin lands in S7-01 (`vulnerability-remediation--node--npm`) with a real digest entry." Phase-3 S7-01 has landed — the phrasing is stale. AC-3(a) corrects it in place; do not leave the stale wording untouched (accumulating stale docs is a common failure mode of "additive" work).
- **Performance:** `compute_plugin_tree_digest` is O(plugin-tree-size); the Phase 7 plugin is small (~10 files at S5-04 landing). Negligible cost. No perf budget concern.
- **JSON formatting stability:** Regenerate `PLUGINS.lock` deterministically via `json.dumps(data, sort_keys=True)` (no indentation — mirror the existing single-line format). Deterministic key order makes future PR diffs minimal and reviewable; sorted keys also make the fence test's expected-shape assertions stable.
