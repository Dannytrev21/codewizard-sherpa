# Story S9-02 — Chainguard catalog file-hash fence (final pin, tamper detection)

**Step:** Step 9 — CVE-to-image catalog YAML + loader + file-hash fence
**Status:** Ready
**Effort:** S
**Depends on:** S5-04 (the `tests/fence/test_phase7_chainguard_lookup_table_loads.py` placeholder file with `_CATALOG_SHA256_PLACEHOLDER` + `xfail(strict=True)` markers + `## TODO(S9-02)` hand-off block); S9-01 (the actual `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` file whose bytes this story pins).
**ADRs honored:** Phase 7 ADR-0010 (CVE-to-image lookup ships as plugin-internal frozen YAML; file-hash fence at CI time is the named tamper defense); Phase 7 ADR-0011 (no Chainguard credential class — this fence is the only operator-side tamper defense Phase 7 ships, and that is deliberate); Phase 7 ADR-0009 (the byte-edit allowlist that makes this fence's reach surgical — only the catalog YAML and the pinned-hash line are CODEOWNERS-refreshable); Phase 3 ADR-0011 (honest framing — this is integrity attestation, NOT cryptographic signature; CODEOWNERS is the social anchor; Sigstore is deferred); Phase 7 ADR-0005 (the catalog and its fence both live under the plugin tree).

## Context

S5-04 planted the placeholder. S9-01 landed the YAML. This story closes the loop: replace the all-zero `_CATALOG_SHA256_PLACEHOLDER` with the actual sha256 of `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml`, strip the two `xfail(strict=True)` markers, and prove the fence catches a deliberately-planted byte-edit. After this story, any modification to the catalog YAML that does NOT also bump the pinned hash in this fence file fails CI; the only legitimate path through CI is a single CODEOWNERS-reviewed PR that touches both the YAML and the fence's pinned-hash constant in lockstep (S9-03 documents that workflow).

**Honest framing — Phase 3 ADR-0011 carry-forward (mandatory).** This fence is **integrity attestation, not a cryptographic signature.** It detects accidental corruption, partial-merge errors, and unreviewed file changes. A determined adversary with merge rights on `main` defeats it trivially by editing both files in the same PR. The social anchor is `.github/CODEOWNERS` requiring a named reviewer on both paths; the cryptographic anchor (Sigstore-bundled signed artifact) is **deferred per Phase 7 ADR-0010** to a future ADR. Do not over-claim the property in the test docstring, the module docstring, the commit message, or the catalog-refresh-process doc that S9-03 writes. The Phase 3 ADR-0011 framing is canonical; mirror it.

**Why this story is small.** S5-04 did the heavy lifting: the test file exists, the path constants are pinned, the import shape is wired, the `make fence` collection picks it up, the `## TODO(S9-02)` block enumerates exactly five mechanical steps for the implementer. S9-02 is the swap-and-prove story: compute the real hash, replace the constant, remove the xfail markers, demonstrate red-on-tamper and green-on-pristine. The story is intentionally a short mechanical hand-off; if it grows past a half-day of work, something is wrong with the S5-04 hand-off and that is the conversation to surface.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases row 9` — "CVE-to-image YAML signature poisoned (file edited outside CODEOWNERS PR)" — names this fence as the defense, the Sigstore upgrade as the deferral.
  - `../phase-arch-design.md §Adversarial test design — "Poisoned CVE-to-image YAML"` — names this fence by file path.
  - `../phase-arch-design.md §Tradeoffs (consolidated) row "Frozen YAML CVE-to-image lookup"` — "operator-side tamper detection via file-hash fence."
- **Phase ADRs:**
  - `../ADRs/0010-chainguard-cve-image-lookup-frozen-yaml.md §Decision + §Consequences` — names this fence as the load-bearing tamper defense; names the Sigstore upgrade as deferred (do not violate the deferral).
  - `../ADRs/0011-no-chainguard-credential-class.md §Decision` — names the public-pull discipline this fence does NOT extend; the fence's scope is the YAML's bytes, not the registry's authenticity.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — the catalog YAML is allowlisted for CODEOWNERS refresh; the fence's pinned-hash line is a one-line edit in the same PR.
- **Sibling stories:**
  - `S5-04-plugins-lock-and-catalog-hash-placeholder.md` — the placeholder this story finalizes. AC-4 and AC-4.b name the five mechanical steps; AC-5.c explicitly defers the planted-violation proof to this story.
  - `S9-01-chainguard-catalog-and-loader.md` — the YAML whose bytes this story pins. The seeded row + ` extra="forbid"` Pydantic loader are S9-01's job; this story does not touch the loader.
  - `S9-03-catalog-refresh-process-doc.md` — the operator-facing process this fence's hash-update step is documented by.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `tests/fence/test_phase7_chainguard_lookup_table_loads.py` — the placeholder S5-04 planted. Read cover-to-cover. The five mechanical steps under `## TODO(S9-02)` are the implementation outline of this story.
  - `plugins/PLUGINS.lock.README.md §"Honest framing"` — the canonical honest-framing wording; mirror in this fence's module docstring.
  - `tests/fence/test_phase7_plugin_lock_row_present.py` (from S5-04) — precedent for a "compute hash on disk; compare to pinned constant; CODEOWNERS-gated refresh" fence. Mirror the test shape.
- **Production ADRs:**
  - `../../../production/design.md §2.6 — Organizational uniqueness as data, not prompts` — the parent rule. Catalog is data; fence is the integrity attestation; humans refresh via PR.

## Goal

Replace the `_CATALOG_SHA256_PLACEHOLDER` constant in `tests/fence/test_phase7_chainguard_lookup_table_loads.py` with the actual sha256 of the catalog YAML S9-01 landed, remove the two `xfail(strict=True)` markers, and prove via planted-violation evidence that (a) on the pristine tree, both tests pass green; (b) a one-byte mutation to the YAML produces an immediate CI-time hard fail naming the mismatch; (c) the only path back to green is a coordinated edit to both the YAML and the pinned-hash constant in the same PR (which CODEOWNERS gates per S9-03).

## Acceptance criteria

### Hash computation + pinning

- [ ] AC-1 — `tests/fence/test_phase7_chainguard_lookup_table_loads.py::_CATALOG_SHA256_PLACEHOLDER` is renamed to `_CATALOG_SHA256_PINNED` (the placeholder-vs-pinned distinction matters; future readers grepping for "placeholder" should not find this constant after S9-02 lands). The value is the actual `hashlib.sha256(<catalog-yaml-bytes>).hexdigest()` of the file S9-01 shipped, prefixed `sha256:` to match the `ImageDigest` convention from S1-01 (`sha256:<64-hex>`).
- [ ] AC-2 — The hex digest is computed via `hashlib.sha256(Path(_CATALOG_PATH).read_bytes()).hexdigest()` — a direct file-bytes hash. NOT `compute_plugin_tree_digest` (that's a directory-walk hash and is the wrong tool here — the catalog is one file). Document in the module docstring the reason for the choice: a single-file file-bytes hash is the simplest defense that detects byte-level tamper; a tree-walk hash would over-collect under refactors and defeat the defense's purpose.
- [ ] AC-3 — The hash constant has an inline comment naming the YAML's git SHA at story-landing time (`# Pinned against catalog YAML at git <short-sha>; refresh via S9-03 process`). The comment is informational only; the test does not depend on git state.

### Test shape — markers stripped, assertions tightened

- [ ] AC-4 — `test_catalog_file_exists`: the `@pytest.mark.xfail(strict=True, reason="Catalog YAML lands in S9-01")` marker is **removed**. The test now asserts `_CATALOG_PATH.exists()` and `_CATALOG_PATH.is_file()` and passes green on the pristine tree. (If the file does not exist, the test fails hard — that IS the desired failure mode if S9-01 was reverted.)
- [ ] AC-5 — `test_catalog_hash_matches_pinned`: the `@pytest.mark.xfail(strict=True, reason="Placeholder hash; S9-02 will pin the real value")` marker is **removed**. The test computes `hashlib.sha256(_CATALOG_PATH.read_bytes()).hexdigest()` and asserts equality with `_CATALOG_SHA256_PINNED[len("sha256:"):]` (strip the prefix). Failure message names both expected and observed digests so a refresh PR's reviewer can sanity-check the diff at a glance.
- [ ] AC-6 — A third test `test_catalog_loader_accepts_pinned_file` is added: it calls `from plugins.distroless_migration_node_npm.data.loader import load_chainguard_catalog, default_catalog_path` and asserts `isinstance(load_chainguard_catalog(default_catalog_path()), Ok)`. This wires the fence to the S9-01 loader's happy-path round-trip — a refresh that breaks schema validity (e.g., introduces a malformed entry) fails this test even if the hash is updated. Belt-and-braces: hash detects tamper, loader detects schema regression. Both are cheap.

### Module docstring + honest-framing discipline

- [ ] AC-7 — The module docstring is rewritten (the `## TODO(S9-02)` block is removed; that hand-off is consumed). The new docstring states:
  - The purpose: pin the catalog YAML's sha256 at CI time; detect any tamper.
  - The honest framing: this is **integrity attestation, not a cryptographic signature** — Phase 3 ADR-0011 carry-forward; verbatim wording from `plugins/PLUGINS.lock.README.md §"Honest framing"` adapted for this fence.
  - The Sigstore deferral: a one-line pointer to Phase 7 ADR-0010 §Consequences ("Sigstore-signed-artifact upgrade deferred to a future ADR").
  - The refresh path: a one-line pointer to `docs/phases/07-migration-task-class/catalog-refresh-process.md` (S9-03's doc); CODEOWNERS gates the catalog YAML and this fence's pinned-hash line together.
- [ ] AC-8 — No over-claim. The docstring does not use the words "signed," "signature," "cryptographically verified," "tamper-proof," or "non-repudiable." It does use "integrity attestation," "tamper-detection," "CODEOWNERS-gated." Surface conflicts via Rule 7, do not silently average them; the Phase 3 ADR-0011 framing is the more recent, more tested pattern and is the canonical voice. (If a previous draft used the over-claim wording, this story strips it.)

### Planted-violation evidence — Rule 12 fail-loud

- [ ] AC-9 — On a throwaway branch, mutate one byte of `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` (e.g., flip a single character in the `notes:` field; add a trailing whitespace; mutate one digit of the `image_digest` hex). Run `pytest tests/fence/test_phase7_chainguard_lookup_table_loads.py` — `test_catalog_hash_matches_pinned` fails. Capture the failure output (expected vs observed sha256, both named). Record the red git SHA + the captured output in `_attempts/S9-02.md` as a 5–10 line evidence block.
- [ ] AC-10 — Revert the mutation. Run again. Test green. Record the green git SHA + the captured output. This pair (red SHA + green SHA + matched terminal output) is the load-bearing demonstration that the fence is detecting real byte-level drift, not just always-passing.
- [ ] AC-11 — Repeat the planted-violation cycle with a schema regression: introduce a malformed entry (e.g., remove `notes` key) in the YAML. Run again. `test_catalog_loader_accepts_pinned_file` fails (the loader returns `Err`). Verify `test_catalog_hash_matches_pinned` ALSO fails (since the bytes changed). Both failure modes co-detect; record output.

### Refresh workflow validation

- [ ] AC-12 — Manually walk through the legitimate-refresh path on the throwaway branch: (a) edit the YAML to add a second row (use a plausible second CVE + Chainguard image — pick from the published Chainguard advisories matching the e2e fixture context); (b) recompute `hashlib.sha256(<file>).hexdigest()`; (c) update `_CATALOG_SHA256_PINNED` in the fence file to the new value. Run `pytest tests/fence/test_phase7_chainguard_lookup_table_loads.py` — all three tests green. Verify `make check` green. Discard the branch. This proves the refresh process works mechanically; S9-03 documents it for operators.
- [ ] AC-13 — Verify the byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) DOES NOT FIRE on the legitimate-refresh path: the catalog YAML and the fence's pinned-hash line are both outside the 10-row code allowlist (the YAML is plugin data; the fence file is in `tests/fence/`). Verify by running the byte-edit fence against the AC-12 throwaway branch; it should exit 0. Document in `_attempts/S9-02.md`.

### Gating + structural conformance

- [ ] AC-14 — `pytest --collect-only tests/fence/test_phase7_chainguard_lookup_table_loads.py` reports exactly three collected items (down from the two xfail-strict items S5-04 planted; the third is the new loader-round-trip test from AC-6). Drift in this count is a regression and surfaces immediately.
- [ ] AC-15 — `ruff format`, `ruff check`, `mypy --strict tests/fence/test_phase7_chainguard_lookup_table_loads.py` all clean. The file imports only from `hashlib`, `pathlib`, `pytest`, `plugins.distroless_migration_node_npm.data.loader`, and `codegenie.result` — no LLM SDK, no broader dependencies.
- [ ] AC-16 — `make fence`, `make check` both green on the pristine tree.
- [ ] AC-17 — `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (S5-01) reports no flagged edits attributable to this story. The story edits ONLY `tests/fence/test_phase7_chainguard_lookup_table_loads.py` — a file the byte-edit allowlist does not gate (it is in `tests/fence/`, not in the 10-row locked surface of Phase 0–6.5 code paths).
- [ ] AC-18 — TDD red test exists, committed, and is now green: the red bar at story-start is "with the placeholder hash + xfail markers, running the fence after stripping markers without updating the hash should fail." The green bar is "with the real hash pinned, all three tests pass; with a one-byte mutation to the YAML, the hash test fails immediately."

## Implementation outline

1. **Read the S5-04 placeholder cover-to-cover.** `tests/fence/test_phase7_chainguard_lookup_table_loads.py` is the file; the `## TODO(S9-02)` block is the recipe. Verify the five mechanical steps S5-04 enumerated are still accurate (S5-04's framing is authoritative; deviations are surfaced via Rule 7, not silently averaged).
2. **Verify S9-01 landed.** `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` exists and is loadable. Run `pytest tests/unit/plugins/distroless_migration_node_npm/test_catalog_loader.py` — green. If not green, S9-02 is blocked on S9-01 stabilizing — surface immediately.
3. **Compute the real sha256.** `python -c "import hashlib, pathlib; print('sha256:' + hashlib.sha256(pathlib.Path('plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml').read_bytes()).hexdigest())"`. Capture the value verbatim.
4. **Rename the constant.** `_CATALOG_SHA256_PLACEHOLDER` → `_CATALOG_SHA256_PINNED`. Replace the all-zero value with the real value from step 3. Add the inline `# Pinned against catalog YAML at git <short-sha>` comment.
5. **Strip the xfail markers.** Remove `@pytest.mark.xfail(strict=True, ...)` from both `test_catalog_file_exists` and `test_catalog_hash_matches_pinned`. Tighten the assertions per AC-4 + AC-5 (named expected-vs-observed in the failure message).
6. **Add `test_catalog_loader_accepts_pinned_file`** (AC-6). One assertion; ≤ 8 LOC.
7. **Rewrite the module docstring.** Strip the `## TODO(S9-02)` block. New docstring per AC-7 + AC-8. Mirror the `plugins/PLUGINS.lock.README.md §"Honest framing"` voice. Cite Phase 3 ADR-0011, Phase 7 ADR-0010, Phase 7 ADR-0011, and S9-03's catalog-refresh-process doc.
8. **Run `pytest tests/fence/test_phase7_chainguard_lookup_table_loads.py` — green.** All three tests collected, all pass. AC-14's collection count of 3 verified.
9. **Plant the violation (AC-9 + AC-10).** Throwaway branch; mutate one byte of the YAML; run the fence; record output; revert; run again; record output. Both go into `_attempts/S9-02.md` as the load-bearing evidence.
10. **Schema-regression violation (AC-11).** Throwaway branch; introduce a malformed entry; verify both `test_catalog_hash_matches_pinned` AND `test_catalog_loader_accepts_pinned_file` fail; record output.
11. **Legitimate-refresh walkthrough (AC-12).** Throwaway branch; add a second row; recompute the hash; update the pinned constant; verify all three tests green; verify `make check` green; discard the branch.
12. **Verify cross-fence non-regression (AC-13 + AC-17).** Run `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` against the AC-12 legitimate-refresh branch; it exits 0 (the YAML and the fence file are outside the 10-row allowlist). Document the path-filter behavior in `_attempts/S9-02.md`.
13. **Run `make check` on the pristine post-S9-02 tree.** Green. Story done.

## TDD plan — red / green / refactor

### Red — failing test first

The red bar for this story is *already planted* by S5-04: the two `xfail(strict=True)` markers fire as "expected failure" today; remove the markers without updating the hash and the tests turn into hard failures (placeholder hash `sha256:00...00` does not match the real YAML's sha256). The story's first move is to make red explicit:

```python
# Step 1 — make the failure mode visible.
# In tests/fence/test_phase7_chainguard_lookup_table_loads.py:
#   - Remove the @pytest.mark.xfail markers from both tests.
#   - Do NOT yet update _CATALOG_SHA256_PLACEHOLDER.
# Run: pytest tests/fence/test_phase7_chainguard_lookup_table_loads.py -x
# Expect: test_catalog_hash_matches_pinned FAILS with "sha256 mismatch:
#   expected sha256:00...00, observed sha256:<real>".
# This is the red bar — explicit, named, reproducible.
```

### Green — minimum impl

Replace `_CATALOG_SHA256_PLACEHOLDER` → `_CATALOG_SHA256_PINNED` with the value from `hashlib.sha256(...).hexdigest()`. Re-run the test. Green. Add the `test_catalog_loader_accepts_pinned_file` test (AC-6). Green. Iterate AC-9 → AC-13 cycles on throwaway branches; record evidence in `_attempts/S9-02.md`.

### Refactor — clean up

- Module docstring rewrite per AC-7 + AC-8: integrity-attestation framing, no over-claim.
- Inline `# Pinned against catalog YAML at git <short-sha>` comment (AC-3) — informational only.
- Confirm the three tests are individually descriptive: `test_catalog_file_exists`, `test_catalog_hash_matches_pinned`, `test_catalog_loader_accepts_pinned_file`. A future reader scanning failure output should be able to tell from the test name alone which of the three failure modes (missing file, byte-level tamper, schema regression) fired.
- Confirm `mypy --strict` clean. The fence test uses only stdlib types + `Path` + `Ok` from `codegenie.result`; no `Any` is needed.

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_phase7_chainguard_lookup_table_loads.py` | The placeholder S5-04 planted; this story finalizes it. Real hash pinned; xfail markers stripped; third test added; module docstring rewritten with honest framing. |
| `_attempts/S9-02.md` | Append-only attempt log: AC-9 + AC-10 planted-violation evidence (red SHA + green SHA + terminal output), AC-11 schema-regression evidence, AC-12 legitimate-refresh walkthrough, AC-13 + AC-17 byte-edit-fence non-regression note. |

**No other files edited.** This story does NOT touch the catalog YAML (S9-01 owns that), the loader (S9-01 owns that), the catalog-refresh-process doc (S9-03 owns that), the `PLUGINS.lock` file (S5-04 owned that), or the byte-edit allowlist fence (S5-01 owns the allowlist; this story consumes its non-flagging behavior, not amends it).

## Out of scope

- **The actual catalog YAML content + the loader.** S9-01's territory. This story only pins the hash of whatever S9-01 ships.
- **The catalog-refresh-process operator doc.** S9-03's territory. This story's module docstring points at S9-03's doc by relative path; the doc's content is S9-03's job.
- **Sigstore-bundled signed-artifact upgrade.** Explicitly deferred per Phase 7 ADR-0010 §Consequences ("The deferred ADR for the Sigstore upgrade is named ('Phase 7 ADR-0007 placeholder — Sigstore-signed CVE-to-image artifact, deferred')"). Do not start it here; do not pre-shape the loader for it; do not extend the fence to expect a `.sigstore` companion file.
- **Live registry verification.** Phase 7 ADR-0011 rules out a Chainguard credential class entirely; pulls happen at `DistrolessBuildGate`-time via Phase 2's existing registry-pull capability. This fence pins YAML bytes, not registry authenticity.
- **Lock-file regeneration tooling (`codegenie plugins lock-update` or `codegenie catalog hash-refresh`).** Manual `hashlib.sha256(...)` + paste-into-constant is the documented Phase 7 mechanism (per S9-03). Automated tooling is Phase 11 territory.
- **Multiple catalog files / per-distro-shard catalogs.** Phase 7 ships one YAML; one pinned hash. Sharding is a Phase 8+ conversation gated by an ADR amendment.

## Notes for the implementer

- **Read S5-04's `## TODO(S9-02)` block first.** It enumerates five mechanical steps; this story is the execution of those five steps plus the evidence-capture cycle. Do not re-derive the steps; trust S5-04's hand-off and surface deviations rather than silently re-inventing the wheel (Rule 7).
- **Honest framing is non-negotiable.** Read `plugins/PLUGINS.lock.README.md §"Honest framing"` and Phase 3 ADR-0011 before writing the docstring. The wording "integrity attestation, not cryptographic signature" is the canonical phrase. Do NOT use "signed," "signature," "tamper-proof," or "non-repudiable" anywhere in this story's artifacts.
- **Single-file file-bytes hash, NOT tree-walk hash.** `compute_plugin_tree_digest` is for `PLUGINS.lock` (a directory attestation); this fence is for one file (a single-file content attestation). Mixing the two confuses the threat model and breaks the refresh workflow — a single-byte edit to the YAML should fail the fence even if no other file changed. Document the choice in the docstring (AC-2).
- **Inline comment with git SHA is informational only.** AC-3's `# Pinned against catalog YAML at git <short-sha>` is a debugging aid for reviewers (it lets them grep the git history for when the hash was last updated). The test does NOT depend on git state; do not write a test that calls `git rev-parse` or inspects `.git/`.
- **Three tests, three failure modes.** `test_catalog_file_exists` catches "S9-01 was reverted"; `test_catalog_hash_matches_pinned` catches "byte-level tamper"; `test_catalog_loader_accepts_pinned_file` catches "schema regression that happens to keep the file present and the hash updated." All three are cheap; ship all three.
- **Planted-violation evidence is the load-bearing demonstration.** Rule 12 fail-loud. Do not skip the throwaway-branch cycle; capture red SHA + green SHA + terminal output verbatim in `_attempts/S9-02.md`. A reviewer reading the attempt log should be able to reproduce the cycle in 5 minutes.
- **Don't over-claim the byte-edit fence's reach.** The byte-edit allowlist (S5-01) is for code edits to Phase 0–6.5 Python/JSON/TOML surface; the catalog YAML and `tests/fence/` files are outside it by design. If you find yourself wanting to add an 11th allowlist row to "cover" the catalog YAML, stop — that's an ADR violation (the CODEOWNERS mechanism + this fence is the defense). Surface in `_attempts/S9-02.md` if a reviewer pushes for an allowlist row addition.
- **Coordinate with S9-03's writer.** S9-03 documents the operator-facing refresh process; this fence's module docstring points at S9-03's doc by relative path. If S9-03 lands first, verify the path is correct; if this story lands first, leave the path as `docs/phases/07-migration-task-class/catalog-refresh-process.md` and S9-03 will fulfill that pointer.
