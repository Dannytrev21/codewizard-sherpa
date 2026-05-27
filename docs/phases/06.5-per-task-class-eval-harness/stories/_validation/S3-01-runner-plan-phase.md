# Validation report — S3-01 (Runner plan phase: load + digest + cache-key compute)

**Validated:** 2026-05-27
**Validator:** scheduled `story-validation-corrector` task
**Story:** `docs/phases/06.5-per-task-class-eval-harness/stories/S3-01-runner-plan-phase.md`
**Verdict:** **HARDENED**
**Findings:** 26 total — 6 blocks, 16 hardens, 4 nits

## TL;DR

The story's *goal* is clean and traces precisely to `phase-arch-design.md §Components → runner.py` step 1 and to ADRs 0001/0002/0010. The *prescribed implementation*, however, calls functions and references attributes that **do not match the contracts the HARDENED predecessor stories (S2-01..S2-06) actually shipped**. Most defects are not "the story is wrong" — they are "the story was drafted against an earlier (pre-validation) shape of S2-03/S2-04 and never re-grounded after those stories were hardened."

Six structural BLOCKS (all in-place fixable):

1. **F-CON-1.** Story calls `compose_cache_key(case_digest=..., sut_digest=..., ...)` (6 kwargs). HARDENED S2-03 replaced that with `compose_cache_key(inputs: CacheKeyInputs) -> CacheKey` (one frozen aggregate). Signature does not exist.
2. **F-CON-2.** Story reads `chain_result.head` from `audit.verify(...)`. HARDENED S2-04's `VerifyResult` has fields `(ok, verified_complete, verified_incomplete, tampered_path, reason)` — there is **no `.head`** field, and no public head-read primitive exists yet. Resolution: extend `audit.py` by addition with `audit.read_chain_head(out_dir) -> str`.
3. **F-CON-3.** Story asserts `exc.value.file_path.name.startswith("2")` on the raised `ChainTamperDetected`. HARDENED S1-01 + S2-04 pin `ChainTamperDetected` as a **marker-only** Exception (no custom `__init__`, no named attributes); the discipline is positional args + `ei.value.args[N]`. The story's test would `AttributeError` at runtime.
4. **F-CON-4.** Story uses `"0" * 64` literal in the implementation outline. HARDENED S2-04 establishes `GENESIS_PREV_HASH: Final[str]` in `codegenie.hashing`. Must consume.
5. **F-CON-5.** Story step 7 calls `codegenie.hashing.blake3_tree(cassette_root)`. **This helper does not exist** in `src/codegenie/hashing.py` (closest existing: `content_hash` per-file, `content_hash_of_inputs` for a manifest-not-content fingerprint, `tree_digest_of_files` which takes pre-materialized `(relpath, bytes)` pairs and returns un-prefixed hex). The cassette-corpus digest must be defined precisely — and adding a `content_hash_tree(root, *, glob)` helper is the cheapest way to do it without re-implementing the chokepoint elsewhere.
6. **F-CON-6.** Story step 6 says `rubric_digest = BLAKE3(concat(rubric.py, breakdown_keys.py, failure_modes.yaml))`. Bare-byte concatenation of three files is a **boundary-shift hazard** — `rubric.py="A"`+`breakdown="BC"` collides with `rubric.py="AB"`+`breakdown="C"`. Must compose through `identity_hash(*parts)` (which prepends an arity byte + UNIT_SEP) or compose via `tree_digest_of_files` (which length-prefixes each record). The bare-BLAKE3 phrasing is silently wrong.

Plus 16 hardenings (coverage gaps, mutation-resistance weaknesses, mock-target-at-import-site, primitive obsession, helper undefined), and four nits.

The fixes are all in-place — no goal change, no scope change. **HARDENED.**

## Stage 1 — Context loaded

Read in this order:

- `S3-01-runner-plan-phase.md` (target).
- `phase-arch-design.md` §Component design → `runner.py` (line 572), `audit.py` (line 618), `cache.py` (line 603); §Data model (line 733); §Control flow (line 824); §Edge cases #11/#17 (line 954/960); §Testing strategy (line 968).
- ADRs `0001` (subprocess isolation), `0002` (lower_bound_95 / deterministic seed), `0010` (isolation_class annotation).
- `stories/_validation/S2-02-loader-cases-and-digests.md` (HARDENED) — `load_cases(task_class: TaskClass)` signature, failure ordering, `BenchCaseDigestMismatch` carries `case_id`/`expected`/`computed`.
- `stories/_validation/S2-03-content-addressed-cache.md` (HARDENED) — **`compose_cache_key(inputs: CacheKeyInputs) -> CacheKey`** aggregate signature replaces the 6-kwarg shape; `CacheKey = NewType("CacheKey", str)` newtype; `__all__` locked at `("CacheKey", "CacheKeyInputs", "compose_cache_key", "get", "put", "gc")`.
- `stories/_validation/S2-04-audit-chain-extension.md` (HARDENED) — `ChainTamperDetected` is **marker-only** (no named attrs); `VerifyResult` has no `.head` field; `codegenie.hashing.chain_identity` + `GENESIS_PREV_HASH` are the canonical primitives; private `_current_head(out_dir) -> tuple[str, Path|None]` exists inside `audit.py` but is **not public**.
- `stories/S2-01-bench-import-path-resolution.md` — `load_task_class(name, bench_root=Path("bench"), *, registry: TaskClassRegistry | None = None) -> TaskClass`. The `registry=` DI kwarg is the canonical test-isolation seam.
- `src/codegenie/hashing.py` — confirms `blake3_tree` does **not** exist; `content_hash`, `content_hash_bytes`, `content_hash_of_inputs`, `identity_hash` (with arity-byte + UNIT_SEP), `tree_digest_of_files` (un-prefixed) are the available primitives.
- `tests/helpers/` is empty on disk (the `chain.py` / `bench.py` helpers referenced by the story do not yet exist — first-mention is in the S3-01 TDD plan).

**Context Brief:**

S3-01 is the first concrete consumer of the entire Phase 6.5 substrate (errors, models, loader, cache, audit, hashing extensions). Its goal — a pure planning function that gates the run on chain integrity and case digests before any SUT call — is exactly what `phase-arch-design.md` step 1 of `run_eval` describes. But the story was drafted before S2-03/S2-04 were validated and never re-grounded; it cites signatures that no longer exist. This is the validation pass that re-grounds the story.

Rule-of-three lineage:

- `compose_cache_key` (S2-03) is the first concrete *aggregate-and-hash* composer; S3-01's `run_id` derivation is the second; any future `evidence_key` would be third. **Not yet** rule of three; **but** the story must consume `compose_cache_key`'s aggregate pattern rather than open-code a new bare-BLAKE3 join.
- `audit.read_chain_head(out_dir)` does not yet exist; this story is the *first* consumer that needs to read the head without writing — Phase 9 (Temporal durable workflow) will be the second. Adding the primitive here is extension by addition.
- `content_hash_tree(root, *, glob)` does not yet exist; this story is the first consumer; Phase 9's blob-ref store or any future bundle-hash use case could be the second. Adding the helper in `codegenie.hashing` keeps the chokepoint clean.

**Open ambiguities:** Two — both resolvable without going back to the user:

- **A1:** Does the audit-head reader belong in this story or in an S2-04 amendment? Pragmatic answer: this story. S2-04 is HARDENED but **not yet GREEN** — its public surface is still being shipped. Adding `read_chain_head` as a new public name in `audit.__all__` (alongside `write_run_record` and `verify`) is extension by addition for S2-04. The implementer running S3-01 will land it.
- **A2:** Does the cassette-corpus digest helper belong in this story or in S2-04 / Phase 0 `hashing.py`? Pragmatic answer: in `codegenie.hashing` (additive). This story consumes it. Phase 0's `hashing.py` already owns the chokepoint discipline (ADR-0001); adding `content_hash_tree` extends it.

Both A1 and A2 are pinned in the hardened ACs and the implementer notes; both have explicit fence-test obligations.

## Stage 2 — Critic findings

### Coverage critic — 8 findings (1 block, 6 harden, 1 nit)

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-COV-1 | block | No AC for the empty-bench (`load_cases(tc) == ()`) path. The story's prescribed dict-comprehension `{case.case_id: ... for case in cases}` produces `cache_keys == {}`; nothing tests that this is acceptable, nor that `run_id` is still derivable, nor that `plan(...)` doesn't crash. Empty bench is a legitimate state during early Phase 7 / new-task-class scaffolding. | New AC-12 added — `plan(...)` over a zero-case bench returns a RunPlan with `cases==()`, `cache_keys=={}`, and a valid 16-hex `run_id`. |
| F-COV-2 | harden | No AC asserts that `plan.cases` is **sorted by `case_id`**. The dataclass docstring claims it; `load_cases` (HARDENED S2-02 AC-16/17) guarantees it; but the plan story doesn't transitively pin it (a future refactor of plan could re-shuffle). | New AC-13 — `tuple(c.case_id for c in plan.cases) == sorted(c.case_id for c in plan.cases)`; mirrored as a hypothesis property over shuffled load_cases inputs. |
| F-COV-3 | harden | No AC pins where `prev_chain_head` comes from when the chain exists and is tamper-free (the post-genesis happy path). Only genesis path is touched. | New AC-14 — happy-path: write r1 via `audit.write_run_record`; call `plan(...)`; assert `plan.prev_chain_head == chain_identity(...)` recomputed from r1 via the oracle. |
| F-COV-4 | harden | No AC for `BenchCaseDigestMismatch` propagation. AC-4 names the abort order but no test exercises the digest-mismatch path (only the chain-tamper path). | New AC-15 — `BenchCaseDigestMismatch` from `load_cases` propagates from `plan(...)` unwrapped (no try/except swallowing) before any digest computation. Mirrors AC-4's tamper-path test. |
| F-COV-5 | harden | No AC for `BenchCaseIDCollision` propagation (HARDENED S2-02 AC-8). Same abort-order concern as F-COV-4. | New AC-16 — collision raised by `load_cases` propagates unwrapped. |
| F-COV-6 | harden | No AC for the `harness_version` shape — empty string, leading/trailing whitespace, non-`str` would silently flow into `run_id` and `cache_key` composition. | New AC-17 — `harness_version` must be a non-empty `str` matching `^[0-9a-z][0-9a-z.+-]*$` (CalVer-or-SemVer; permissive); empty / `None` / `bytes` → `TypeError` at plan entry. |
| F-COV-7 | harden | The "abort order" AC-4 says verify-before-load_task_class and load_cases-mismatch-before-digest but the implementation outline lists *six* steps after verify. The full abort chain (verify → load_task_class → load_cases → sut_digest → rubric_digest → cassette_corpus_digest → run_id → cache_keys) is not pinned positionally. A faulty impl that computes `sut_digest_fn()` (an injected callable) before `load_cases` would pay a needless cost on poisoned-bench runs. | New AC-18 — `sut_digest_fn` MUST NOT be called when `load_cases` raises. Asserted by `sut_digest_fn = Mock(side_effect=lambda: pytest.fail("must not be called"))`. |
| F-COV-8 | nit | No AC for the `bench_root` shape (missing dir, non-Path). | Deferred to caller validation — `load_task_class` (S2-01) already validates `bench_root`. Surfaced in implementer notes. |

### Test-Quality critic — 8 findings (2 block, 5 harden, 1 nit)

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-TQ-1 | block | `_stable_plan_args()` is called in four tests but **never defined**. Same anti-pattern HARDENED S2-02 (F-TQ-3..F-TQ-12) and S2-04 (F-TQ-1) explicitly flagged. A `pass`-body `plan(...)` would fail every test with `NameError` before exercising the actual function — the tests aren't testing what they claim to test. | Pinned in TDD plan: `_stable_plan_args(tmp_path)` is a module-level helper that scaffolds a `tests/helpers/bench.py:stub_task_class_fixture(tmp_path)` 3-case bench, seeds a clean chain via `tests/helpers/chain.py:seed_clean_chain(out_dir)`, and returns the kwargs dict for `Runner().plan(**...)`. Shape pinned in the hardened TDD plan. |
| F-TQ-2 | block | `test_plan_run_id_is_16_hex_chars_of_blake3` is trivially passable by `return "0" * 16` or `return "deadbeefcafebabe"`. The test only asserts shape, not derivation. | Rewritten to recompute the expected `run_id` independently via the oracle: `expected = compute_run_id_oracle(task_class, sut_digest, rubric_digest, cassette_corpus_digest, run_started_iso)`; assert `plan.run_id == expected`. The oracle uses the same primitive the impl is required to use (`identity_hash(...)[:16]` after stripping the `sha256:` prefix and the arity-byte composition — see AC-2 rewritten). |
| F-TQ-3 | harden | `monkeypatch.setattr("codegenie.eval.cache.put", ...)` patches **at the module of definition**. If `runner.py` does `from codegenie.eval.cache import put`, the patch silently misses (a Python pytest classic). The story doesn't pin the import convention. | Implementer notes pin the convention: `runner.py` imports the *module* (`from codegenie.eval import audit, cache`), not the symbols. Tests patch at `codegenie.eval.cache.put` and `codegenie.eval.audit.write_run_record` correspondingly. AC-22 (test convention) added. |
| F-TQ-4 | harden | `test_plan_rubric_digest_flips_on_one_byte_edit_to_breakdown_keys` only tests one of the three files. Mutant: an impl that hashes only `rubric.py` + `breakdown_keys.py` (forgetting `failure_modes.yaml`) passes. | Parametrize over all three files: `@pytest.mark.parametrize("filename", ["rubric.py", "breakdown_keys.py", "failure_modes.yaml"])`. |
| F-TQ-5 | harden | No mutation-resistance test for the **cache_key composition** at the plan layer. S2-03 has it at the helper layer; plan-layer test that swaps `sut_digest` and `rubric_digest` values verifies plan wires them in the correct positions. | New test parametrized over `itertools.combinations` of swappable digest pairs; mirrors S2-03's positional-swap pattern. |
| F-TQ-6 | harden | The test `test_plan_does_not_invoke_sut_or_cache_or_audit_write` patches three sinks but doesn't track call order. A mutant that calls `load_task_class` *after* `sut_digest_fn()` would still pass. | Replace with an ordered call log: pass instrumented spies into all collaborators; assert call order matches the canonical abort sequence. |
| F-TQ-7 | harden | `test_plan_is_byte_identical_across_two_calls_with_identical_inputs` compares via `json.dumps(dataclasses.asdict(...), sort_keys=True)`. This catches most non-determinism but a hypothesis property over varying-but-stable inputs is stronger (catches non-determinism in dict iteration order for `cache_keys` under different `case_id` sets). | New hypothesis property test — generate a shuffled case-id list, run `plan(...)` twice, assert byte-identical. |
| F-TQ-8 | nit | The story's regression test `asserts the comment exists` (AC-8 second sentence) — brittle and verifies the wrong thing. The behavioural invariant is "isolation_class is NOT in cache_key composition," which is observable. | AC-8 rewritten as a *behavioural* assertion: build two RunPlans with the same inputs but conceptually-different isolation classes; assert `cache_keys` are byte-identical. Comment-presence test deleted. |

### Consistency critic — 7 findings (3 block, 3 harden, 1 nit)

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-CON-1 | **block** | `compose_cache_key` signature mismatch with HARDENED S2-03 (`(inputs: CacheKeyInputs) -> CacheKey`, not 6 kwargs). The test as written would `TypeError`. | AC-6 + Implementation outline rewritten. Plan constructs `CacheKeyInputs(case_digest=..., sut_digest=..., ...)` from `S2-03`'s aggregate; calls `compose_cache_key(inputs)`; receives `CacheKey`. |
| F-CON-2 | **block** | `chain_result.head` does not exist on `VerifyResult`. No public head-read primitive in HARDENED S2-04. | AC-19 added (extension by addition): `codegenie.eval.audit.read_chain_head(out_dir: Path) -> str` is a new public primitive returning `GENESIS_PREV_HASH` for empty chains and `chain_identity(...)` of the lexicographically-greatest record otherwise. Implemented in terms of S2-04's private `_current_head`. Added to `audit.__all__`. Phase 9 will be the second consumer (extension by addition). |
| F-CON-3 | **block** | `ChainTamperDetected.file_path` attribute access conflicts with S1-01 marker-only discipline (re-affirmed by HARDENED S2-04 F-CON-1). | Test rewritten: `ei.value.args[0] == str(out_dir / "<some chain file name>")` (positional); no attribute access. AC-4 reworded — `plan` raises `ChainTamperDetected` constructed positionally as `ChainTamperDetected(str(tampered_path or out_dir), expected_head, "verify-not-ok")` matching S2-04's pattern. |
| F-CON-4 | **block** | `"0" * 64` literal usage in implementation outline. HARDENED S2-04 establishes `GENESIS_PREV_HASH` in `codegenie.hashing`. | Implementation outline rewritten to consume `GENESIS_PREV_HASH`. No literal in `runner.py`. |
| F-CON-5 | **block** | `codegenie.hashing.blake3_tree` does not exist. Story would fail import. | AC-20 added: a new public helper `codegenie.hashing.content_hash_tree(root: Path, *, glob: str = "**/*", follow_symlinks: bool = False) -> str` returning `blake3:<hex>` over a sorted-by-relpath stream of `(relpath, bytes)` tuples composed via `tree_digest_of_files` (then re-prefixed). Story step 7 consumes it. The helper is the chokepoint extension for "directory tree → BLAKE3 digest." Added to `hashing.__all__`. |
| F-CON-6 | **block** | Bare BLAKE3 of `rubric.py || breakdown_keys.py || failure_modes.yaml` is boundary-shift unsafe. | AC-5 + Implementation outline rewritten to compose via `tree_digest_of_files` over a length-prefixed `(relpath, bytes)` stream (same primitive the new `content_hash_tree` uses) or via `identity_hash_bytes(content_hash_bytes(r) + content_hash_bytes(b) + content_hash_bytes(f))`. Pinned: `identity_hash` family is the canonical boundary-safe composer. |
| F-CON-7 | harden | Story's `bench_root: Path` parameter is mandatory but `load_task_class` (S2-01 AC-1) defaults `bench_root=Path("bench")`. Consistency: either default in plan too, or document why plan demands the explicit value. | Story keeps `bench_root` mandatory at the plan layer — plan is the orchestrator boundary where the CLI passes the resolved-explicit value (S4-02 owns the default). Documented in implementer notes. |
| F-CON-8 | harden | Story does not thread `registry=` kwarg through to `load_task_class`. S2-01 AC-16 established this DI seam for clean test isolation; the plan story doesn't expose it. Tests will be forced to monkeypatch `default_registry`. | AC-21 added: `plan(...)` accepts optional `registry: TaskClassRegistry | None = None`; passes through to `load_task_class`. When `None`, falls back to `default_registry`. Mirrors S2-01's pattern. |
| F-CON-9 | nit | Story implementation step 4 says `structlog.bind(run_id=...)`. HARDENED predecessors use `structlog.testing.capture_logs()` testing (F-COV-8 of S2-03). The plan's log event should have a pinned event id (`runner.plan_complete`) and an entry in `_WARNING_IDS: Final[frozenset[str]]` per the Phase 1 `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` regex. | Implementation outline step 4 amended — module-level `_EVENT_IDS: Final[frozenset[str]] = frozenset({"runner.plan_complete"})`; validated at import via `raise AssertionError(...)` (bare `assert` is forbidden). |

### Design-Patterns critic — 7 findings (0 block, 6 harden, 1 nit)

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-DP-1 | harden | **Primitive obsession.** `RunPlan.cache_keys: Mapping[str, str]` ignores the `CacheKey = NewType("CacheKey", str)` newtype HARDENED S2-03 ships. | AC-1 amended: `cache_keys: Mapping[str, CacheKey]` (the outer key stays raw `str` because the `CaseId` newtype is phase-wide-deferred per S2-06 F-CON-6 / S2-02 line 506). Re-exports `CacheKey` from `codegenie.eval.cache`. |
| F-DP-2 | harden | **`run_id: str`** is also primitive-obsessed. Per CLAUDE.md "Never raw `str` for domain IDs." | `RunId = NewType("RunId", str)` added to `codegenie.types.identifiers` (mirrors `CacheKey`, `ProbeId`); `RunPlan.run_id: RunId`; `_compose_run_id(...) -> RunId` smart constructor. |
| F-DP-3 | harden | **Functional core / imperative shell.** Plan mixes pure logic (digest composition, cache-key derivation, run_id derivation) with impure I/O (verify chain, load_task_class side effect, load_cases filesystem walk). The pure halves deserve direct unit tests. | Implementation outline extracts three pure helpers: `_compose_rubric_digest(rubric_path, breakdown_path, failure_modes_path) -> str`, `_compose_cassette_corpus_digest(cassette_root) -> str` (consumes the new `content_hash_tree`), `_compose_run_id(task_class_name, sut_digest, rubric_digest, cassette_corpus_digest, run_started_iso) -> RunId`. Each is bytes-in → digest-out; tested directly. |
| F-DP-4 | harden | **Open/Closed at the audit-head boundary.** Today the plan reads the head from `audit.verify(...)` (which doesn't expose one). Phase 9's durable workflow will need the same read. Coupling the head-read to `verify` (a tamper-detection function) muddles the two responsibilities. | The new `audit.read_chain_head(out_dir) -> str` (AC-19) is the explicit port: one job (read), one signature, both this story and Phase 9 consume by addition. |
| F-DP-5 | harden | **Smart-constructor / illegal-states-unrepresentable.** `RunPlan` permits `cache_keys.keys() != {c.case_id for c in cases}` — a wrong impl that derives keys from `range(len(cases))` builds a representable-but-broken RunPlan. | AC-1 amended with a `__post_init__` invariant: `set(cache_keys.keys()) == {c.case_id for c in cases}`; mismatch → `ValueError`. Fence-test asserts the invariant fires. |
| F-DP-6 | harden | **Dependency-inversion / injection for the audit + loader collaborators.** Currently `runner.py` imports `audit` and `loader` modules directly. Test isolation requires monkeypatching at the import site (F-TQ-3). A thin `RunnerCollaborators` aggregate (dataclass with `audit: AuditModuleProtocol`, `loader: LoaderModuleProtocol`, ...) would be a cleaner port. | **Deferred.** Today's only consumer is the plan method; rule-of-three not met (Phase 9's durable workflow would be the second). Surfaced in implementer notes as the trigger condition; F-TQ-3's import-site-patch convention is the simpler fix today. |
| F-DP-7 | nit | The `Runner` class with one method (`plan`) is a function dressed as a class. | **Accepted as-is.** The arch design has Runner as a 6-phase orchestrator (plan, cache probe, execute, aggregate, cost cap, audit append); plan is just phase 1. Future stories (S3-02..S3-06) will land the other methods on the same class. Documented in implementer notes. |

## Stage 3 — Researcher

**Not invoked.** Every finding maps to an in-repo precedent:

- Aggregate signatures + smart constructors — S2-03.
- Marker-only Exception positional-args discipline — S1-01 + S2-04.
- Chain primitive + `GENESIS_PREV_HASH` — S2-04.
- Hashing chokepoint discipline (UNIT_SEP, arity byte, length-prefixed records) — Phase 0 `hashing.py` ADR-0001.
- DI registry kwarg — S2-01.
- Mock-target-at-import-site convention — pytest classic; S2-03 / S2-06 test-quality findings.
- Hypothesis property tests for determinism — S2-02 AC-17, S2-04 AC-14.
- Pure / impure split — every HARDENED phase-6.5 story.
- Sum types for `_current_head` — surfaced as deferred (rule-of-three not met) in S2-04.
- Functional core / imperative shell — explicit in HARDENED S2-06 F-DP-1.

## Stage 4 — Conflict resolution + synthesis

Priority chain (per `editor.md`): **Consistency > Coverage > Test-Quality > Design-Patterns**.

| Conflict | Resolution |
|---|---|
| Coverage (F-COV-1: empty bench) vs Consistency (silent on this) | Coverage wins — no ADR forbids empty bench; the path is legitimate and silently passable. |
| Test-Quality (F-TQ-3: import-site patch) vs Design-Patterns (F-DP-6: inject collaborators) | Rule 2 / rule-of-three wins. Plan is the *first* concrete consumer of audit+loader at the orchestrator boundary; injection is YAGNI today. The patch-at-import-site convention is the cheaper today-fix. F-DP-6 demoted to implementer note. |
| Consistency (F-CON-2: add `audit.read_chain_head`) vs S2-04 surface lock | S2-04 is HARDENED but not GREEN; the public-surface lock is `("read_chain_head", "verify", "write_run_record")` *after* this story lands the addition. Extension by addition; no conflict. |
| Consistency (F-CON-5: add `content_hash_tree`) vs Phase 0 hashing chokepoint | Phase 0 ADR-0001 IS the chokepoint; adding `content_hash_tree` extends it. The new helper composes via existing chokepoint primitives (`tree_digest_of_files` then re-prefix). No conflict — exactly the extension-by-addition pattern Phase 0 invites. |
| Design-Patterns (F-DP-1/F-DP-2: newtypes) vs phase-wide `TaskClassName`/`CaseId` deferral | DP wins on `CacheKey` (S2-03 already shipped the newtype — no deferral). DP wins on `RunId` (new addition this story); falls in line with `CacheKey`, `ProbeId` precedent. `CaseId` stays deferred per S2-02 / S2-06 precedent — the outer key in `cache_keys: Mapping[str, CacheKey]` is raw `str` for now. |

No `NEEDS RESEARCH` findings; no stage 3 invocation.

## Edits applied

The story file was edited in place via `Edit` calls. Summary:

| Section | Before | After |
|---|---|---|
| Header | `Status: Ready` | `Status: Ready (HARDENED 2026-05-27)`; Depends-on extended to include S1-01, S1-02, S1-03, S2-01, S2-03; ADRs honored line clarified. |
| Validation notes | (none) | New block inserted under header summarizing every change with finding IDs. |
| Goal | unchanged | unchanged (the goal is correct; only the AC formulation needed hardening). |
| Acceptance criteria | 11 bullets, signature mismatches throughout | 22 numbered ACs — 6 BLOCKs fixed, 6 hardenings, 5 new ACs for missing edges, 5 new ACs for the kernel additions (`audit.read_chain_head`, `content_hash_tree`, `RunId` newtype, `__post_init__` invariant, event-ID validation). |
| Implementation outline | 5 steps, bare-BLAKE3 phrasing | 7 numbered steps — `GENESIS_PREV_HASH` consumed, `content_hash_tree` consumed, `compose_cache_key(CacheKeyInputs)` consumed, three pure helpers extracted (`_compose_rubric_digest`, `_compose_cassette_corpus_digest`, `_compose_run_id`), import-site convention pinned. |
| TDD plan | 6 thin tests with undefined `_stable_plan_args()` | 13 tests — `_stable_plan_args(tmp_path)` defined with concrete shape; oracles for `run_id` and `prev_chain_head`; parametrize over the three rubric files; ordered-call-log purity test; hypothesis determinism property; behavioral isolation-class-not-in-cache-key; empty-bench path; happy-path beyond-genesis. |
| Files to touch | 5 entries | 8 entries — adds `src/codegenie/types/identifiers.py` (new `RunId`), `src/codegenie/hashing.py` (add `content_hash_tree`), `src/codegenie/eval/audit.py` (add `read_chain_head`), `tests/fence/test_runner_plan_invariants.py` (fence for `__post_init__` + event-ID regex). |
| Out of scope | 4 bullets | 7 bullets — each deferred concern names the owner story (S3-02 fan-out, S3-05 bootstrap, etc.) and the extraction trigger (DP F-DP-6 rule-of-three for collaborator injection). |
| Notes for the implementer | 6 bullets | 11 bullets — adds the marker-Exception discipline reminder, mock-target convention, runner-class-justification, DP-F-DP-6 trigger condition, harness_version validation rationale, primitive-obsession deferral note for `CaseId`. |

## Verdict rationale

The story prescribes a small, focused planning function with a clean contract that maps 1:1 to `phase-arch-design.md §runner.py step 1`. The defects are entirely in the story's *prescribed implementation* — it was drafted against an earlier (pre-validation) shape of S2-03 and S2-04, and never re-grounded. Every BLOCK is in-place fixable; no goal change required.

After hardening, the story:

- Consumes the HARDENED `compose_cache_key(CacheKeyInputs) -> CacheKey` aggregate signature instead of the non-existent 6-kwarg shape.
- Lands two new kernels by addition: `codegenie.eval.audit.read_chain_head(out_dir)` and `codegenie.hashing.content_hash_tree(root, *, glob)`. Both have fence-test coverage; both have a documented second-consumer trigger (Phase 9 durable workflow).
- Uses the marker-only `ChainTamperDetected` discipline correctly (positional args, `ei.value.args[N]` assertions).
- Replaces bare-BLAKE3 concatenation with the boundary-safe `tree_digest_of_files` / `identity_hash` composition.
- Introduces `RunId` as a domain newtype + smart constructor (`_compose_run_id`); promotes `cache_keys` to `Mapping[str, CacheKey]`.
- Has mutation-resistant red tests: parametrized over the three rubric files (not just one), ordered call log for purity (not just sink-spy), hypothesis property for determinism, behavioral test for isolation-class-not-in-cache-key (not a comment-grep regression test).
- Pins `__post_init__` invariant on `RunPlan` (cache_keys.keys() == cases case_ids) — makes the broken state unrepresentable.
- Threads `registry=` kwarg through plan → load_task_class for clean test isolation (mirrors S2-01 AC-16).
- Defers `RunnerCollaborators` injection aggregate cleanly (rule-of-three not met) with named trigger condition (Phase 9 as second consumer).

Ready for `phase-story-executor`.
