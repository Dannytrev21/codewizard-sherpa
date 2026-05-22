# Validation report: S4-04 — YAML canonical records + `manifest.yaml` with BLAKE3 chain head

**Validated:** 2026-05-22
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-04 extends S4-03's `ChromaPersistentStore.add()` so a single call atomically writes (1) the canonical YAML record, (2) chromadb, (3) `manifest.yaml` with a BLAKE3-rolled `chain_head` over the canonical YAML bytes in insertion order. It rewires `_load_existing_record_ids()` to read the manifest, lands a Hypothesis YAML-roundtrip property, and adds `SolvedExample.from_yaml()`. The goal traces cleanly to ADR-0016 (YAML canonical / chromadb derived — the "content-addressed derived-index" pattern), arch §Component 7, the §"On-disk shapes" block, and the §"Property tests" entry. The architectural shape is **sound** — no scope rewrite — so this is HARDENED, not RESCUE.

But the story carried **5 block-severity defects** and a cluster of **harden**-severity gaps. Every one was fixable in place. The load-bearing problems: a `mypy --strict` type contradiction the story never addressed (`digest() -> StoreDigest` returning a `ChainHead`); an AC-5 test that is self-fulfilling by construction (both `chain_head` and `digest()` delegate to the same helper, so the equality check passes for a *wrong* helper); an AC-8 "prefix property" that no test actually exercised; an entire crash-recovery negative space (manifest-write failure, missing record file, malformed manifest) promised in prose but pinned by no AC; and `from_yaml` shipped with zero tests.

22 findings — 5 block, 13 harden, 4 nit.

## Findings by critic

### Consistency critic

**C1 (block) — `digest() -> StoreDigest` cannot return a `ChainHead` under `mypy --strict`.** S4-03 AC-6 (HARDENED) + arch §Component 7 pin the Protocol method `def digest(self) -> StoreDigest`. S4-04 AC-5 + Outline §2/§7 define `_compute_chain_head(...) -> ChainHead` and say "both `digest()` and `manifest.write` call it." `StoreDigest` and `ChainHead` are **distinct S1-01 newtypes** — S1-01's mypy-negative suite explicitly parametrizes the `StoreDigest ← ChainHead` swap as an error. So `def digest(self) -> StoreDigest: return _compute_chain_head(...)` is a hard `mypy --strict` failure, and AC-11 requires mypy clean. The story was silent on the wrap. **Resolution:** AC-5 + Outline §7 now pin `return StoreDigest(_compute_chain_head(...))` — same BLAKE3 hex, re-typed to the Protocol's domain newtype, with the lift commented. Making `digest()` return `ChainHead` was rejected (would mutate S4-03's frozen Protocol + its AC-9 `inspect.signature` fence).

**C2 (harden) — S4-04 rerolls S4-03's `digest()` contract; the cross-story amendment must be recommended, not applied.** S4-03 AC-6 currently rolls BLAKE3 over record-ID *strings*; S4-04 rerolls over canonical YAML *bytes*. S4-03's hardening *anticipated the order-source change* (AC-3 caveat + Notes §11 defer cross-process determinism to S4-04's manifest), but **not** the byte-basis change (IDs → YAML bytes). AC-5's "Cross-story divergence" clause now states this; Notes §1 already carried the rationale. The validator does not edit S4-03 — see "Recommended cross-story amendments" below.

**C3 (nit) — `schema_version` is a manifest field beyond ADR-0016's quoted shape.** ADR-0016 §Consequences pins `{records: [...], chain_head: ChainHead}`; arch line 789 repeats it. S4-04 adds `schema_version: 1`. Adding a struct field is sanctioned extension-by-addition (CLAUDE.md), and AC-9's unknown-version → `StoreCorrupted` is a fail-loud forward-compat hook — so no story edit. But the ADR's own quoted shape is now stale; see "Recommended cross-story amendments."

**C4 (nit, confirmation) — new YAML + manifest writes are inside the existing `asyncio.Lock`.** ADR-0016 §Decision mandates single-writer `add()`. Outline §5 places all three writes "after lock acquired" inside S4-03's existing lock. No concurrency hole. AC-4 now adds a clause noting the `_record_ids.append` + manifest write are sequenced after the chromadb call inside the same lock hold, so no separate rollback is needed.

**C5 (harden) — `_Manifest` placement + no `from_yaml`.** `_Manifest` is correctly module-private in `store.py` (a store-internal durability artifact); `SolvedExample.from_yaml` is correctly on the public model in `models.py` (S4-07 consumes it). The gap: the story should say `_Manifest` deliberately gets **no** `from_yaml` classmethod so the executor doesn't mirror it and bloat the private type. Outline §6 now states this.

**C6 (nit, confirmation) — `StoreCorrupted` first-exerciser.** S4-03 declared `StoreCorrupted` but (per its validation report C4) never exercised it — corruption recovery was explicitly forecast as "S4-04/S4-07 work." S4-04 AC-9/AC-13 are the first exercisers. Consistent; the error type is reused, not forked (Files-to-touch confirms).

### Coverage critic

**V1 (block) — manifest-write-failure path promised in Context, pinned by no AC.** Context (story line 19) promised "On manifest-write failure, the next `add()` recomputes the manifest from scratch." AC-2 covered only the happy path; AC-4 covered *chromadb*-fails-after-YAML but not *manifest*-write-fails-after-chromadb. Worse, the promised recovery is only half-true: in-process the next `add()` self-heals (because `_record_ids` still holds the id), but across a process restart the stale manifest silently under-counts a chromadb-committed record. **Resolution:** added **AC-12** pinning the honest semantics (YAML + chromadb on disk, manifest stale, re-raise; in-process self-heal vs cross-process `rag rebuild` reconciliation) and corrected the Context sentence.

**V2 (block) — a manifest referencing a missing record file crashes `digest()` with a raw `FileNotFoundError`.** AC-3 populates `_record_ids` from the manifest; `_compute_chain_head` then `read_bytes()`-es each `<id>.yaml`. If the manifest lists an id whose file is absent, the first `digest()` or `add()` after reopen leaks `FileNotFoundError` — not a typed error (Rule 12 violation). **Resolution:** added **AC-13** (→ `StoreCorrupted`), and Outline §2's `_compute_chain_head` now translates `FileNotFoundError` → `StoreCorrupted`.

**V3 (harden) — only unknown `schema_version` was covered; truncated/structurally-broken manifests were not.** `_load_existing_record_ids` does `yaml.safe_load` then `_Manifest.model_validate`; a truncated file raises `yaml.YAMLError`, a missing `records` key raises `pydantic.ValidationError` — neither is `StoreCorrupted`. **Resolution:** AC-9 broadened to cover *all* malformed cases → `StoreCorrupted`.

**V4 (harden) — stale `.tmp` from a crashed write unspecified.** Harmless here (`os.replace` overwrites; `_load_existing_record_ids` reads the manifest, not a `records/*.yaml` glob) but should be *stated* so a reviewer doesn't add a glob that enumerates `.tmp`. **Resolution:** Notes §9 added.

**V5 (harden) — record-id path-traversal unguarded.** AC-1 writes `<root>/records/<example.id>.yaml`; an id with `/` or `..` escapes `records/`. The Hypothesis strategy uses a hex alphabet so the property would never catch it. **Resolution:** added **AC-14** — defers to `SolvedExampleId`'s S1-01 hex smart constructor if the model enforces it, else `add()` rejects a non-hex id before any write; either way one test proves `id="../../etc/passwd"` cannot reach a write.

**V6 (block, = test-quality T3) — AC-10 `from_yaml` has no test.** See T3.

**V7 (harden) — AC-5 silently revises a shipped story.** AC-5 now requires `make test` green for the **whole** `tests/unit/rag/` suite after the `digest()` rewrite (an S4-03 `digest()` test asserting ID-string semantics would otherwise stay red). See also C2 and the cross-story amendment.

**V8 (harden) — empty-store / single-record boundary uncovered.** AC-7 pinned 3 records, AC-8 pinned 10; nothing pinned the empty store (does it even have a `manifest.yaml`? what is `digest()`?). **Resolution:** added **AC-15** — empty store: `_record_ids == []`, no `manifest.yaml`, `digest()` = empty-chain constant; after first `add()`, `manifest.yaml` exists.

**V9 (nit) — AC-2's manifest dump options didn't match AC-1's.** Outline §5 dumped the manifest without `default_flow_style`/`allow_unicode`, unlike the record write — a byte-identity hazard for AC-7. **Resolution:** AC-2 + Outline §5 now spell out identical options.

### Test-Quality critic

**T1 (block) — AC-5's `test_chain_head_equals_digest_after_add` is a consistency check, not a correctness check.** Both `chain_head` and `digest()` delegate to `_compute_chain_head`; if that helper is wrong (rolls over IDs, sorts records, hashes-each-then-XORs), the equality still holds. No test pinned `chain_head` to an *independently computed* value. **Resolution:** added the mandatory `test_chain_head_is_blake3_of_concatenated_canonical_yaml` oracle — recomputes `blake3(b"".join(...))` in the test body with a deliberately non-sorted insertion order (`ex-b` then `ex-a`) so a `sorted()` mutant fails. The original test is kept but documented as "necessary, not sufficient."

**T2 (block) — AC-8's "prefix property" was claimed but untested.** The follow-on test only collected 10 chain heads and asserted distinct; a mutant rehashing all records on every `add()` still yields 10 distinct heads. The prefix property is untestable inside one store. **Resolution:** AC-8 split into two contracts; prefix-stability is pinned (a) against the new *pure* `_roll_chain_head` core with synthetic bytes, and (b) a two-store cross-check.

**T3 (block) — AC-10 `from_yaml` shipped with zero tests.** The TDD plan's follow-on list named tests for AC-1..AC-9 but none for AC-10. **Resolution:** AC-10 + the follow-on list now require a round-trip test and a negative (`ValidationError`) test.

**T4 (harden) — AC-1's sorted-keys check was too weak.** `first_key == sorted(body.keys())[0]` checks one key; on CPython 3.11/3.12 `next(iter(dict))` reflects YAML-stream order, so a `sort_keys=False` mutant can pass if the first-dumped field happens to sort first. **Resolution:** AC-1 + the Red test now assert the **full** top-level key ordering on the raw text.

**T5 (harden) — AC-6's `builds()` strategy may silently under-cover.** `st.builds(SolvedExample, ...)` will fail or generate degenerate values on newtype / `EmbeddingVector` / nested-`RecordProvenance` / `datetime` fields if any field is left to inference. **Resolution:** AC-6 now requires an explicit per-field strategy (mirroring the repo's sum-type roundtrip precedent), an inline non-degeneracy assertion, and `@settings(max_examples=50, deadline=None, database=None)`.

**T6 (harden) — AC-7's byte-identity test risked comparing parsed dicts.** The Red-section sibling compares `yaml.safe_load(...)` dicts; if the AC-7 follow-on copies that, `sort_keys`/float-format divergence is hidden. **Resolution:** AC-7 now explicitly requires `read_bytes()` comparison, no `safe_load`.

**T7 (harden) — AC-4's failure-path assertion set was incomplete.** "manifest does not list `example.id`" is vacuously true on a first-ever add (no manifest exists) and also true of a manifest that *was* written. **Resolution:** AC-4 now pins two distinct cases — first-add (manifest absent) and Nth-add (manifest bytes unchanged) — and requires a *named* exception type, not bare `Exception`.

**T8 (nit) — Red docstring overclaimed.** `test_add_writes_canonical_yaml_record_first` claimed it "Catches wrong-write-order mutants" but never asserts order. **Resolution:** docstring corrected; write-order is proved by the AC-4 chromadb-failure test.

### Design-Patterns critic

**D1 (harden) — pure-impure tangle: `_compute_chain_head` was called a "pure helper" but does file I/O.** AC-5/AC-7/AC-8 all hinge on the *roll* being correct, yet every test had to stage real files. **Resolution:** Outline §2 now splits a pure `_roll_chain_head(Iterable[bytes]) -> ChainHead` core (functional core — table-testable, no fs) from the I/O shell `_compute_chain_head`; AC-8's prefix property is pinned against the pure core.

**D2 (harden) — reinvented atomic-write helper.** `src/codegenie/probes/layer_d/conventions.py` already ships a byte-identical `_atomic_write_text`; this would be the ~8th per-module copy. **Resolution:** Outline §4 now says "mirror `layer_d/conventions.py`, do not redesign," drops the hidden `.parent.mkdir` from inside the helper (caller mkdirs `records/` explicitly — AC-1), and flags a shared `codegenie/_fsutil.py` consolidation as a sanctioned-migration candidate **out of scope** for S4-04 (Rule 3). The codebase has *already chosen* per-module copies, so a local helper is consistent — but the proliferation is recorded.

**D3 (nit) — O(N) re-read per `add()` → O(N²) ingest.** Deliberately *not* optimized: a running hasher would be hidden mutable state that can desync from disk and make `digest()` silently lie. The stateless re-read is more correct and stays inside ADR-0016's `add() < 50 ms` budget at Phase-4 corpus sizes. **Resolution:** Notes §10 records the rationale so a future contributor doesn't "optimize" it into a correctness bug.

**D4 (harden) — `schema_version` check-ordering hazard.** `_Manifest` is `extra="forbid"` + `schema_version: Literal[1]`; a v2 manifest would fail `model_validate` with a generic `ValidationError` *before* the intended `StoreCorrupted` diagnostic. **Resolution:** AC-9 + Outline §6 now sequence the raw `schema_version` check **before** `_Manifest.model_validate`. Notes §8 amended to say no dispatch table now (Rule 2 — one version).

**D5 (harden) — `from_yaml`/`to_yaml` asymmetry; AC-6 never exercised `from_yaml`.** The Goal advertised `from_yaml(to_yaml(x)) == x` but AC-6 tested a hand-inlined `safe_dump`. **Resolution:** `_canonical_yaml_dump` promoted from Refactor to the Green path as the single serialization surface; AC-1, AC-2, AC-6, and `from_yaml`'s parse core all route through the shared helpers, so the property now guards the real code.

**D6 (nit, confirmation) — `StoreDigest` vs `ChainHead` are legitimately distinct.** They denote different concepts (the live store's identity vs the manifest's content head) that the system asserts *coincide* — that coincidence is exactly what AC-5 pins. Not anaemic duplication. Both shipped in S1-01; the validator cannot redefine them. Recorded so the synthesizer doesn't mistake it for a defect.

**D7 (nit) — `_load_existing_record_ids` untyped-dict shuffling.** `yaml.safe_load` returns `Any`; a YAML scalar/list (corrupt file) reaches `model_validate` and leaks `ValidationError`. Folded into D4 / AC-9's defensive-parse requirement (wrap `yaml.YAMLError`, assert mapping, translate `ValidationError`).

## Research briefs

No `NEEDS RESEARCH` findings. Every issue resolved from in-repo sources: ADR-0016 (canonical/derived split, manifest shape, perf envelope), S4-03 story + its validation report (`digest()` semantics, `StoreCorrupted` deferral, Protocol surface), S1-01 (`StoreDigest`/`ChainHead` newtype distinctness + mypy-negative suite), arch §Component 7 / §On-disk shapes / §Property tests, `src/codegenie/probes/layer_d/conventions.py` (atomic-write precedent), `src/codegenie/cache/keys.py` (BLAKE3 pattern), and the repo's functional-core / fail-loud / extension-by-addition commitments.

## Conflict resolutions

- **Consistency vs. AC-5's "single computation" intent (C1).** AC-5 wanted one `_compute_chain_head`; the Protocol return type forbids `digest()` from returning its `ChainHead` result directly. Resolved by *re-wrapping at the boundary* (`StoreDigest(_compute_chain_head(...))`) — honors the single computation, S4-03's frozen Protocol, and S1-01's newtype distinctness simultaneously. Not averaged.
- **Design-Patterns "don't reinvent" vs. Rule 3 "surgical" (D2).** The atomic-write helper genuinely duplicates an existing idiom, but extracting a shared `_fsutil.py` is out of S4-04's scope. Resolved: keep a local helper (consistent with the codebase's existing per-module choice), mirror the precedent exactly, and record the consolidation as a separate migration candidate.
- **Design-Patterns "incremental hasher" perf idea vs. Rule 2 / correctness (D3).** Resolved in favor of the stateless re-read — it is *more correct* (no hidden state that can desync), not merely simpler.

## Edits applied

1. Header `Status: Ready → HARDENED`; `Validation notes` block inserted summarizing the 5 blocks + key changes + the two cross-story actions.
2. Context §"atomic-write contract" — corrected the manifest-write-failure sentence.
3. AC-1 — route through `_canonical_yaml_dump`; caller mkdirs (not the helper); full-ordering sorted-key assertion.
4. AC-2 — `_compute_chain_head` as the shared computation; manifest dump options spelled out identical to AC-1.
5. AC-3 — malformed-manifest → `StoreCorrupted` forward-reference.
6. AC-4 — renamed to "chromadb-write failure"; two test cases (first-add vs Nth-add); in-lock clause; named exception.
7. AC-5 — rewritten: type re-wrap at the `digest()` boundary; mandatory independent-oracle test; cross-story divergence + whole-suite-green clause.
8. AC-6 — explicit per-field strategy; route through `_canonical_yaml_dump`; key-order-independence scope note; `@settings(... deadline=None, database=None)`.
9. AC-7 — raw-`read_bytes()` comparison, no `safe_load`.
10. AC-8 — split monotonic-unique vs prefix-stable; prefix pinned against the pure `_roll_chain_head` core + a two-store cross-check.
11. AC-9 — broadened to all malformed-manifest cases; `schema_version`-before-`model_validate` ordering.
12. AC-10 — shared parse core; two mandatory tests.
13. **New AC-12** (manifest-write failure), **AC-13** (missing record file), **AC-14** (record-id path safety), **AC-15** (empty-store invariants).
14. Implementation Outline §2 (pure core + I/O shell), §4 (mirror `conventions.py`, no helper-mkdir), §5 (`_canonical_yaml_dump`, in-lock), §6 (defensive parse), §7 (`StoreDigest` re-wrap), §9 (test-coverage map).
15. TDD plan — Red test docstring/assertion fixed; oracle test added; Green/Refactor rewritten; follow-on test list expanded from 6 to 15 sharp tests.
16. Files to touch — `store.py` row updated for the new helper roster.
17. Notes — §8 amended (no dispatch table now; check ordering); §9 (stale `.tmp`) + §10 (O(N) re-read intentional) added.

## Recommended cross-story amendments (validator did NOT apply — one story per invocation)

1. **Amend S4-03 (`S4-03-chroma-persistent-store.md`) AC-6.** Its prose says `digest()` rolls BLAKE3 over record-ID *strings* (`h.update(id.encode("utf-8"))`). S4-04 rerolls over canonical YAML *bytes* via the shared `_compute_chain_head`. Update S4-03 AC-6 prose, Notes §5, and the `digest()` test (`test_digest_is_insertion_order_sensitive`) to the canonical-bytes contract. **S4-04 must not be executed before this is reconciled**, or S4-03's existing `digest()` test will be red against the new contract.
2. **Amend ADR-0016 §Consequences.** The quoted manifest shape `.codegenie/rag/manifest.yaml — {records: [...], chain_head: ChainHead}` is stale — S4-04 adds `schema_version`. One-line edit: `{records: [...], chain_head: ChainHead, schema_version: int}`. (Arch line 789 carries the same stale shape — amend if convenient.)

## Verdict rationale

**HARDENED.** The story's goal, scope, and architectural shape are correct — the content-addressed derived-index pattern is faithfully applied, the writes are correctly placed inside S4-03's single-writer lock, and the YAGNI discipline (no `schema_version` dispatch table, no `_Manifest.from_yaml`, no speculative perf optimization) is sound. No scope rewrite was needed, so this is not a RESCUE. The defects were real but local: one `mypy` type contradiction, three self-fulfilling/absent tests, an entire crash-recovery negative space, and a pure-impure tangle — all patchable in place.

**One caveat the user must action before execution:** recommended cross-story amendment #1 (S4-03 AC-6 reroll). S4-04 is hardened to depend on it explicitly (AC-5's cross-story clause), but executing S4-04 against an un-amended S4-03 will leave S4-03's `digest()` test red.

## Recommended next step

1. Amend **S4-03 AC-6** (and its `digest()` test) to the canonical-YAML-bytes contract — the precondition for S4-04.
2. Optionally amend **ADR-0016 §Consequences** + arch line 789 for the `schema_version` field.
3. Then run `phase-story-executor` on S4-04. (Note S4-03 itself remains blocked on the S1-04 `embedding_vector` amendment from S4-03's own validation report — that chain must clear first.)
