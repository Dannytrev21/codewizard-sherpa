# Story S2-07 — `SCHEMA-EVOLUTION-POLICY.md` + cross-link from sub-schemas

**Step:** Step 2 — Plant skills loader, catalog expansion, schema-evolution policy, and conventions parity lint
**Status:** Ready
**Effort:** S
**Depends on:** S2-01 (`skill.schema.json` exists — cross-links into the policy), S2-04 (the parity lint pattern this policy generalizes), S2-05 (the `schema_version: "v1"` lints enforce what this policy declares)
**ADRs honored:** Gap 1 (cross-phase contract evolution for `ProbeOutput` as Layer B–G slices diverge — this story is the policy document; S2-06 is the cache-key mechanism); ADR-0008 (the CI-gating discipline this policy invokes by reference)

## Context

Gap 1 of `phase-arch-design.md` identifies that as Phase 2's 22 probe classes ship sub-schemas, the **contract evolution** between minor and major schema versions must be a documented policy — not an undocumented norm. Without the policy doc, a future contributor's "small additive field" can quietly land without a version bump or a cache invalidation, and downstream consumers (Phase 4 RAG, Phase 8 hot view) break silently on stale cached evidence.

The policy declares two rules:

1. **Additive evolution → minor bump** (`v1 → v1.1`). New optional field; existing consumers unaffected; cache flushed (per S2-06's mechanism); no Phase ADR amendment required.
2. **Breaking evolution → major bump** (`v1 → v2`). Removed field, changed type, narrowed enum, renamed key, or any other change a consumer could break on. Requires: (a) a Phase-level ADR amendment, (b) a migration handler in the coordinator (`schema_migrate_v1_to_v2(...)`), (c) cache invalidation, (d) a CHANGELOG entry.

The doc cross-links from this phase's README and from every Phase 2 sub-schema's root `$comment`. The S2-05 schema-version lints enforce the declaration shape; this story enforces the **process**.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Gap analysis & improvements" §Gap 1` — the gap statement and proposed remediation; this story is the doc half (S2-06 is the cache-key half).
- **Architecture:** `../phase-arch-design.md §"Integration with Phase 3 (next phase)"` — Phase 3 reads sub-schemas; the policy declares how Phase 3 sees evolution.
- **Phase ADRs:**
  - `../ADRs/0008-conventions-catalog-closed-enum-ci-lint.md` — the lint discipline this policy generalizes from catalogs to all sub-schemas.
  - `../ADRs/README.md` — the phase ADR index; this policy is the meta-policy ADRs reference.
- **Production ADRs:** `../../../production/adrs/` (browse the README for an index) — production ADRs may already reference schema evolution; ensure consistency. If a production-level schema evolution policy doesn't yet exist, this Phase-2 doc is the de facto seed for one.
- **Source design:** `../final-design.md "Departures from all three inputs"` — the synth call-out on schema versioning.
- **Existing code:**
  - `src/codegenie/skills/schema/skill.schema.json` (S2-01) — must cross-link to the policy in its root `$comment`.
  - `src/codegenie/catalogs/conventions/_schema.json` (S2-02) — same.
  - `src/codegenie/catalogs/shell_replacements/_schema.json` (S2-03) — same.
  - `src/codegenie/catalogs/semgrep_rule_packs.schema.json` (S2-03) — same.
  - Phase 2's `README.md` (`docs/phases/02-context-gather-layers-b-g/README.md`, if present) — must cross-link.

## Goal

Land `docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` declaring the v1/v2 evolution rules and the major-bump process, with `$comment` cross-links from every Phase 2 sub-schema root pointing at the doc — verified by extending S2-05's catalog/skill schema-version lints to also assert the cross-link comment is present.

## Acceptance criteria

- [ ] `docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` exists with the following sections at minimum:
  - **Scope:** which artifacts the policy governs (every Phase 2 sub-schema, skill frontmatter schema, catalog schemas).
  - **Versioning shape:** `schema_version: "vN[.M]"` string at root; major is `N`, minor is `.M` (absent ⇒ `.0`).
  - **Additive evolution (minor bump):** what qualifies (new optional field, broadened enum, relaxed constraint), the process (PR + `catalog_version` bump if catalog; cache flushes automatically via S2-06).
  - **Breaking evolution (major bump):** what qualifies (removed field, type change, narrowed enum, renamed key), the process (ADR amendment + coordinator migration handler + CHANGELOG entry + cache invalidation).
  - **Phase 2 starting position:** every Phase 2 sub-schema declares `schema_version: "v1"` (or `enum: ["v1"]` in `_schema.json`).
  - **Lint enforcement:** references S2-05's two lint scripts as the enforcement mechanism for the *declaration*; references S2-06 as the enforcement mechanism for *cache invalidation*; references ADR-0008 as the precedent for the CI-gating pattern.
  - **Worked example:** one minor-bump example (`scip_index` sub-schema gains a new optional field `index_warnings: list[str]` → `v1 → v1.1`) and one major-bump example (`build_graph.resolution_status` enum narrows → `v1 → v2`, migration handler required).
- [ ] The doc is referenced from `docs/phases/02-context-gather-layers-b-g/stories/README.md` (the manifest) — add a "Cross-cutting policies" or "References" section if not already there with a link.
- [ ] Every Phase 2 sub-schema's root `$comment` field references the policy doc with a repo-relative path like: `"Schema-evolution policy: ../../../docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md"`. The four sub-schemas in scope for this story: `skill.schema.json`, `conventions/_schema.json`, `shell_replacements/_schema.json`, `semgrep_rule_packs.schema.json`.
- [ ] S2-05's `check_conventions_schema_versions.py` lint is extended (additively) with one more assertion: the root `$comment` (for `_schema.json`) or the `# Schema-evolution policy: …` header comment (for YAMLs) must reference `SCHEMA-EVOLUTION-POLICY.md`. Missing cross-link → exit 1 with the offending file path. (Skill `*.schema.json` covered by extending the script's walk to include skill schemas; SKILL.md frontmatter need *not* declare it — only schemas/catalogs cross-link.)
- [ ] A synthetic mismatch fixture under `tests/conformance/fixtures/missing_policy_crosslink/` has a `_schema.json` without the cross-link comment; the conformance test asserts the lint goes red.
- [ ] TDD red landed first: the lint extension's new test fails before the cross-links are added; passes after.

## Implementation outline

1. Draft `SCHEMA-EVOLUTION-POLICY.md` per the section list above. Keep it short (300–500 lines max). Borrow the Nygard-ADR voice from the existing `ADRs/` folder where useful, but this is a *policy*, not an ADR — name it as such.
2. Add a "Cross-cutting policies" section to `docs/phases/02-context-gather-layers-b-g/stories/README.md` (or the phase's top-level README if it exists) with a one-line link to the policy doc.
3. Edit each of the four sub-schemas in scope:
   - `src/codegenie/skills/schema/skill.schema.json` — add `"$comment": "Schema-evolution policy: ../../../../docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md"` at root.
   - `src/codegenie/catalogs/conventions/_schema.json` — same, with the appropriate relative path.
   - `src/codegenie/catalogs/shell_replacements/_schema.json` — same.
   - `src/codegenie/catalogs/semgrep_rule_packs.schema.json` — same.
4. Edit each catalog YAML to include a `# Schema-evolution policy: …` comment as the **first line of the file** (after any shebang-style marker, of which there is none for YAML — first line is fine).
5. Extend `scripts/check_conventions_schema_versions.py` (from S2-05) with one more assertion per file: the root `$comment` (JSON) or the first-line comment (YAML) contains the substring `SCHEMA-EVOLUTION-POLICY.md`. Add a `--strict-crosslink` flag (default on in CI) so the test fixture path can opt-out for fixtures that test other invariants in isolation.
6. Add a fixture `tests/conformance/fixtures/missing_policy_crosslink/<file>.schema.json` lacking the cross-link, and an assertion in `tests/conformance/test_schema_version_lints.py` that the lint fails on it.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test additions in `tests/conformance/test_schema_version_lints.py`:

```python
def test_missing_policy_crosslink_fails(tmp_path: Path) -> None:
    fixture = REPO_ROOT / "tests/conformance/fixtures/missing_policy_crosslink"
    result = subprocess.run(
        [sys.executable, str(CATALOG_LINT), "--roots", str(fixture)],
        capture_output=True,
    )
    assert result.returncode == 1
    assert b"SCHEMA-EVOLUTION-POLICY" in result.stderr

def test_real_schemas_have_policy_crosslink() -> None:
    result = subprocess.run([sys.executable, str(CATALOG_LINT)], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
```

Doc-shape "test" is review-time, not CI-time — the doc either has the required sections or doesn't. Author-side discipline + reviewer attention.

Run; confirm red (cross-links absent; fixture absent; lint hasn't been extended); commit; then Green.

### Green — make it pass

Smallest impl: write the policy doc; add four `$comment` cross-links; add YAML header comments; extend the S2-05 lint script with the new assertion; add one fixture. No more.

### Refactor — clean up

- Add a short table-of-contents at the top of `SCHEMA-EVOLUTION-POLICY.md` for navigation.
- Cross-link from the policy doc back to ADR-0008 + S2-06 + the Phase 2 README so the trail is bidirectional.
- Consider promoting the doc to `docs/production/` if/when a second phase needs it (Phase 3 is the test case; defer the promotion until then).
- Run the extended lint locally to confirm it goes green on real files and red on the fixture.

## Files to touch

| Path | Why |
|---|---|
| `docs/phases/02-context-gather-layers-b-g/SCHEMA-EVOLUTION-POLICY.md` | The policy doc itself. |
| `docs/phases/02-context-gather-layers-b-g/stories/README.md` | Add a "Cross-cutting policies" or "References" section linking to the policy. |
| `src/codegenie/skills/schema/skill.schema.json` | Add root `$comment` cross-link. |
| `src/codegenie/catalogs/conventions/_schema.json` | Add root `$comment` cross-link. |
| `src/codegenie/catalogs/shell_replacements/_schema.json` | Add root `$comment` cross-link. |
| `src/codegenie/catalogs/semgrep_rule_packs.schema.json` | Add root `$comment` cross-link. |
| `src/codegenie/catalogs/conventions/node.yaml` | Add `# Schema-evolution policy: …` header comment. |
| `src/codegenie/catalogs/shell_replacements/node.yaml` | Same. |
| `src/codegenie/catalogs/semgrep_rule_packs.yaml` | Same. |
| `scripts/check_conventions_schema_versions.py` | Extend with cross-link assertion. |
| `tests/conformance/fixtures/missing_policy_crosslink/<file>.schema.json` | Fixture lacking the cross-link. |
| `tests/conformance/test_schema_version_lints.py` | Add the missing-crosslink test + the real-schemas pass test. |

## Out of scope

- **Per-probe sub-schemas (`index_health.schema.json`, `build_graph.schema.json`, …)** — land in the respective Step 3/4/5/6/7 stories. Each adds the cross-link comment as part of its own acceptance criterion (this story's lint extension forces it).
- **Migration handler implementation** — deferred until a real `v2` arrives. The policy declares the *requirement*; the *implementation* is per-probe and per-bump.
- **Promoting the policy to `docs/production/`** — defer until Phase 3 actually needs it. Phase 2 owns it locally for now.
- **CHANGELOG infrastructure** — the policy declares the requirement; the CHANGELOG file itself lands when the first major bump happens (or when the project's release process formalizes it).
- **`v1.1` minor-bump example as a working code change** — the policy describes it; this story doesn't ship a `v1.1` sub-schema (none of Phase 2's probes need one yet).

## Notes for the implementer

- **Policy doc voice: declarative, not narrative.** "A breaking change requires X, Y, Z" — not "we believe breaking changes should…". This is a contract, not an essay.
- **The cross-link path is repo-relative**, not absolute. Use `../../../docs/phases/...` from JSON schemas under `src/codegenie/`; verify the path resolves with `Path.resolve()` if unsure. A broken link is silent at runtime but a future contributor's confusion later.
- **`$comment` is a JSON Schema-defined root key.** It's ignored by validators by design — safe to put a free-form string there. Don't put the cross-link in `description` (which some tools render in error messages).
- **YAML header comments are literal text.** `safe_yaml.load` discards them; the lint reads them via `open(path).readline()` (or first few lines). Don't put the comment after the document content — only the first lines are checked.
- **The policy doc is a Phase 2 artifact**, not a global one. If Phase 3 wants to evolve the policy, it amends this doc with a "v0.2" header section or supersedes it; don't pretend it's already production-grade.
- **Major-bump examples should be plausible**, not contrived. The `build_graph.resolution_status` enum narrowing is realistic (Phase 7 might want to forbid `"resolved_with_discrepancy"`); the `scip_index.index_warnings` additive field is realistic (a future SCIP version might surface warnings). Stay in-domain.
- **Don't add a `$schema` reference to `SCHEMA-EVOLUTION-POLICY.md` itself.** It's a Markdown policy doc, not a schema. Resist the urge to over-formalize.
