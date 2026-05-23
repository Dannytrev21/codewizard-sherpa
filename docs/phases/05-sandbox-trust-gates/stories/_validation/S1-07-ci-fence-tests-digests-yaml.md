# Validation report — S1-07 six structural CI fence tests + `tools/digests.yaml` placeholders

**Story:** [`../S1-07-ci-fence-tests-digests-yaml.md`](../S1-07-ci-fence-tests-digests-yaml.md)
**Validated:** 2026-05-23
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S1-07 ships the six **load-bearing** structural CI fence tests that protect every later Phase 5 story (`stories/README.md §Definition of done` re-runs all six on every change), plus the four `tools/digests.yaml` placeholder entries `SandboxHealthProbe` will read at startup. The draft was directionally correct — the six file names match arch §Testing strategy / CI gates exactly, and the deferrals (S5-04 full AST walk, S6-03 digest value validation, S3-05 real `policy_yaml` digest) trace cleanly to later stories. But it had **17 weaknesses across all four critic lenses, six of them block-tier** that an executor following the draft literally would have hit at import time or shipped silently-vacuous tests. The most consequential were:

1. **(consistency — block) Wrong import path for the substring walker.** Draft `test_objective_signals_static.py` calls `from codegenie.sandbox.signals.models import ObjectiveSignals, _iter_nested_field_names`. The HARDENED S1-03 ships **`iter_nested_field_names`** (no leading underscore) in **`codegenie.sandbox.signals._introspection`** (a sibling module, not `models.py`), and S1-03 AC-1b *explicitly forbids* `_iter_nested_field_names` and `iter_nested_field_names` from appearing in `models.__all__`. The draft would `ImportError` on first run — and worse, an executor "fixing" the import by re-declaring the walker locally would silently fork the trust-anchor walker for ADR-0014 (the very risk S1-03 hardened against). Resolution: rewrite the test to import `iter_nested_field_names` from `sandbox.signals._introspection`; call it type-driven (`iter_nested_field_names(ObjectiveSignals)`), not instance-driven via `model_fields[i].annotation`. AC-OS-1 / AC-OS-2.

2. **(consistency — block) Subprocess-chokepoint count drift inside the story.** Story AC text lists **3 chokepoints** (`did/build.py`, `did/network_policy.py`, `firecracker/client.py`) and arch §Tool-use safety also lists 3 — but the draft TDD code block adds a 4th (`firecracker/network_policy.py`). ADR-0009 (Firecracker host-side nftables) is the resolution: it was accepted post the original 3-file decision and adds the 4th file. Either count would have produced a test that drifts vs the actual codebase ADR-0009 produces. Resolution: pin AC text to **4 chokepoints** with explicit ADR-0009 citation; align AC and code block byte-for-byte; document the count growth in Notes. AC-SP-1..AC-SP-4.

3. **(test-quality — block) Zero mutation-resistance — every walker is silently-vacuous on Step 1.** All six fence tests have the same pathology: their scope (`src/codegenie/sandbox/` or `src/codegenie/gates/` or `validation.*` callsites) is **empty or near-empty on the Step 1 codebase**, so a buggy walker (`for node in []`, an `ast.Imp0rt` typo, a `node.module = ""` guard that swallows everything) passes vacuously. A regression that deletes the walker body entirely (`return` at top) still passes. The Phase 0 precedent (`tests/fence/test_no_llm_in_transforms.py`) and the Phase 3 precedent (`tests/fence/test_lint_imports_catches_planted_leak.py`) BOTH ship **planted-positive** tests that prove the walker fires when an offender exists. The draft has none. Resolution: every fence test ships an **in-test planted-positive companion** that constructs a synthetic AST string in-memory (no committed planted files) and asserts the walker returns a non-empty offender list. AC-PP-1..AC-PP-6.

4. **(test-quality — block) Allowlist-bypass property not exercised by `test_env_allowlist_no_credentials.py`.** ADR-0012's belt-and-suspenders is the property that **even if an operator appends `MY_API_KEY` to `ALLOWLIST`**, the deny-substring filter still drops the key (deny runs as an independent gate, not only "skip-if-not-in-allowlist"). The draft only parametrizes denial of keys that aren't in the allowlist anyway — it doesn't `monkeypatch.setattr(env_allowlist, "ALLOWLIST", env_allowlist.ALLOWLIST + ("MY_API_KEY",))` and re-verify rejection. A regression that makes deny *conditional* on "not-in-allowlist" passes the draft test trivially. Resolution: AC-EA-3 + paired test that monkeypatches an offending key INTO the allowlist and re-asserts the filter drops it.

5. **(coverage — block) `test_stage6_chokepoint.py` is doubly-vacuous on Step 1.** (a) The walker scans only `src/codegenie/` for `validation.<attr>` Name-then-Attribute access — but there is currently no `src/codegenie/validation` package or module (the actual Phase 3 Stage 6 entrypoint name is TBD per the story's own Notes), so the walker matches nothing whether buggy or correct. (b) The walker pattern catches `validation.X` but misses `from codegenie.validation import X; X()` and `import codegenie.validation as v; v.X` — both common Python shapes. Resolution: (i) tighten Out-of-scope to make the surface-area gap explicit (S5-04 owns the full ImportFrom + aliased-import walk); (ii) add a planted-positive test that constructs a synthetic AST string `"validation.run_x()"` and asserts the walker fires; (iii) AC-S6-2 explicitly forbids "Phase 3 Stage 6 entrypoint name resolution" from this story — the placeholder enforces shape, not surface coverage. AC-S6-1..AC-S6-4.

6. **(coverage — block) `tests/schema/__init__.py` and `tools/digests.yaml` root-shape unconstrained.** Draft has no AC verifying (a) `tests/schema/__init__.py` exists and is empty, (b) `tools/digests.yaml` root parses to a `dict` (`yaml.safe_load("- a\n- b")` returns a list — `data["sandbox"]` would `TypeError` instead of raising `GateCatalogInvalid`-shaped). Resolution: AC-DG-1 (file exists, package-marker semantics), AC-DG-3 (root must be `dict`), AC-DG-4 (`sandbox` key value must be `dict`).

Beyond the block-tier findings, the harden-tier work:

7. **(coverage — harden) The `_BANNED` set drift hazard.** Story uses `{"anthropic", "langgraph", "chromadb", "sentence_transformers"}` — different from `codegenie._fence.FORBIDDEN_LLM_SDKS` (`{anthropic, langgraph, openai, langchain, transformers}`) by design (different scope: sandbox-and-gates vs gather-pipeline). Without a comment explaining the divergence, a future contributor "fixing" the deny list by importing `FORBIDDEN_LLM_SDKS` would silently *narrow* it (removes `chromadb`, `sentence_transformers`) and silently *widen* it (adds `openai`, `langchain`, `transformers`). Resolution: declare `_BANNED_LLM_IMPORTS: Final[frozenset[str]] = frozenset({"anthropic", "langgraph", "chromadb", "sentence_transformers"})` at module level; AC-LL-2 asserts byte-equality with arch §Development view; module docstring explains the scope divergence vs `FORBIDDEN_LLM_SDKS` (links arch §"Two new top-level packages" + ADR-0008).

8. **(coverage — harden) AST walks catch only eager top-level imports.** The draft tests parse a file and walk for `ast.Import`/`ast.ImportFrom` at any depth — this catches function-body imports too (good), but misses `importlib.import_module("anthropic")`, `__import__("anthropic")`, and dynamic `getattr(__import__("a"), "nthropic")`. Resolution: pin the scope in module docstring + AC-LL-3 ("eager + lazy `import`/`from … import` statements only; `importlib.import_module` / `__import__` belong to a future runtime-import fence — phase-arch-design.md §"AST walk" is authoritative"). Document the limitation; do not over-engineer.

9. **(coverage — harden) `Path` membership in subprocess allowlist is brittle.** Draft compares `py not in ALLOWLIST` where both are absolute `Path` objects from `ROOT / "..."` + `scope.rglob("*.py")`. On case-insensitive filesystems (macOS default) or with symlinks in `ROOT`, the two paths can have different string representations and the membership check silently fails open. Resolution: AC-SP-3 — both sides reduce to `path.resolve().relative_to(ROOT)` (or compared by `str(path.relative_to(ROOT))` against a relative-Path allowlist). Pin in TDD plan.

10. **(coverage — harden) `test_digests_yaml.py` value-shape contract.** Draft asserts only `isinstance(sb[k], str) and sb[k]` — a value of `"x"` or `"not-a-digest"` passes. Step 1 keeps `"TBD"` placeholders explicitly; S6-03 upgrades to BLAKE3 value validation. Pin the placeholder string ("TBD" exact OR a 64-char hex digest) so a partial S6-03 implementation (real digest for `firecracker` but `"TBD"` for `vmlinux`) doesn't silently slip into Step 1's fence. AC-DG-5 / AC-DG-6.

11. **(coverage — harden) Quality-gate AC drift vs all five prior HARDENED Step-1 stories.** S1-02..S1-06 pin `ruff check && ruff format --check && mypy --strict <files> && pytest <test files>` as separate AC bullets. Draft collapses them. Promoted to AC-QG-1..AC-QG-4 matching the established shape; add explicit "no `pytest.mark.skip` / `xfail` markers in `tests/schema/`" mirroring `tests/fence/` discipline.

12. **(consistency — harden) `Depends on` understated.** Draft says `S1-05, S1-06`. The fence tests actually depend on: S1-02 (`ObjectiveSignals` import path stable, `SandboxSpec.env` Mapping shape), S1-03 (`iter_nested_field_names` in `_introspection`), S1-05 (`env_allowlist.filter`, `ALLOWLIST` constant), S1-06 (catalog stub presence — though not directly imported, S1-06 lands the `gates/catalog/` tree this story scopes). Widen to `S1-02, S1-03, S1-05, S1-06`.

13. **(consistency — harden) ADR-0009 missing from `ADRs honored`.** ADR-0009 (Firecracker host-side nftables) is the source-of-truth for the 4th subprocess chokepoint. Add to the honored list.

14. **(design-patterns — harden) Rule-of-three cleared for `tests/schema/_walkers.py` extraction.** Six fence tests share: `ROOT = Path(__file__).resolve().parents[2]`, `_iter_py(roots)` (in two tests verbatim), an `ast.parse(path.read_text())` template. Extract a `tests/schema/_walkers.py` private module with `ROOT: Final[Path]`, `iter_py(*roots)`, `iter_top_level_imports(path)` (yields module-name strings). Each fence test stays a thin "compose walker + assert" body. Phase 7 will add `test_no_secrets_in_distroless_layer.py` and similar — extract at introduction is cheaper than refactor-at-third-additional-file. Rule-of-three IS cleared (6 callers on day one). AC-W-1..AC-W-3.

15. **(design-patterns — harden) Pin `_walkers.py` as the kernel; ban `subprocess`/`os`/`import codegenie.*` imports inside fence tests.** Mirror the S1-02..S1-06 module-purity pattern at the test-file level: `tests/schema/test_*_purity.py` AST-walks every `test_*.py` and asserts its imports are a subset of `{__future__, ast, pathlib, typing, pydantic, yaml, pytest, codegenie.sandbox.signals._introspection, codegenie.sandbox.env_allowlist, codegenie.sandbox.signals.models, tests.schema._walkers}`. Catches the future contributor who tries to short-circuit a fence test by importing the very module it's policing. AC-PU-1.

16. **(design-patterns — harden) `tests/schema/__init__.py` semantics pinned.** New top-level test namespace. Mirror existing convention: empty package marker (the project's `tests/fence/__init__.py` is empty; `tests/unit/schema/__init__.py` is empty). AC-IN-1.

17. **(coverage — nit) Per-test < 1 s runtime AC.** Draft Refactor mentions it; promote to AC-PG-3 — every `tests/schema/test_*.py` collects + executes in < 1 s on the Step 1 codebase. Pin so future additions don't silently bloat the PR critical path.

**No `RESCUE`-tier findings.** Every gap was patchable by tightening ACs, correcting the `_introspection` import path, extracting `_walkers.py`, and adding in-test planted-positive companions.

**No Stage-3 research needed.** Every gap was answerable from Phase 5 arch + ADR-0008/-0009/-0012/-0013/-0014 + the six prior HARDENED reports (S1-01..S1-06) + the codebase precedents in `tests/fence/test_no_llm_in_transforms.py` (runtime-closure walker), `tests/fence/test_lint_imports_catches_planted_leak.py` (planted-positive subprocess pattern), and `tests/unit/test_pyproject_fence.py` (`FORBIDDEN_LLM_SDKS` divergent-scope precedent).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Ship the six structural CI fence tests under `tests/schema/` (LLM-import deny, subprocess-allowlist, `ObjectiveSignals` substring screen, env-allowlist deny-substring, Stage 6 chokepoint placeholder, `tools/digests.yaml` shape) **each with a planted-positive companion proving the walker fires**, a shared `_walkers.py` kernel, the `tests/schema/__init__.py` package marker, and `tools/digests.yaml` with four `sandbox.*` placeholder entries. The six fence tests pass on the Step 1 codebase; the planted positives pass independently; the module-purity test pins the fence tests' own import set; coverage and `mypy --strict tests/schema/` clean.
- **Non-goals (Out-of-scope, hardened):** Real BLAKE3 digests for `vmlinux`/`rootfs`/`firecracker`/`policy_yaml` (S3-05 + S6-03); full AST walk for Stage 6 chokepoint covering `from codegenie.validation import …` + `import … as v` (S5-04); BLAKE3 digest value validation in `test_digests_yaml.py` (S6-03); performance regression tests (S7-01); adversarial tests (S7-01); runtime-import fences for `importlib.import_module(...)` (intentionally deferred — phase-arch-design.md §"AST walk" is authoritative for the static-import-only scope).

### Phase 5 exit criteria touched

- **Step 1 done-criteria (High-level-impl.md §Step 1):** "`pytest tests/schema/` green (six fence/introspection tests pass with empty backends)"; "`tools/digests.yaml` has placeholder entries for `sandbox.firecracker`, `sandbox.vmlinux`, `sandbox.rootfs`, `sandbox.policy_yaml`"; "Static introspection test asserts no field reachable from `ObjectiveSignals` contains `confidence`, `llm`, `self_reported`, or `model_says`."
- **§Goal 8 (arch line 23):** `ObjectiveSignals` Pydantic `extra="forbid", frozen=True` plus CI introspection test — S1-03 ships the local sandbox-tier test; S1-07 ships the schema-tier fence (survives `tests/sandbox/` deletion).
- **§Goal 13 (arch line 28):** zero tokens at the Phase 5 package boundary — the LLM-import deny fence is the structural defense.
- **§Tool-use safety (arch line 844):** subprocess allowlist of exactly the chokepoint files — `did/build.py`, `did/network_policy.py`, `firecracker/client.py`, `firecracker/network_policy.py` (4 files post ADR-0009).
- **§Edge case 19 (arch line 869):** `tools/digests.yaml` missing `sandbox.policy_yaml` → `SandboxHealthProbe` refuses to run — this story ships the presence-only floor; S6-03 the value-shape upgrade.
- **§Testing strategy / CI gates (arch lines 907-914):** six fence file names + AST/introspection logic — byte-exact source-of-truth for this story.

### Load-bearing commitments touched

- **ADR-0008 (LLM judge persona deferral / production ADR-0008):** the LLM-import deny fence is the structural enforcement that no LLM SDK leaks into sandbox/gates. The deny list is `{anthropic, langgraph, chromadb, sentence_transformers}` per arch — **deliberately different from gather-pipeline `FORBIDDEN_LLM_SDKS`** (different scope; `chromadb`/`sentence_transformers` are RAG-stack libraries that must not appear in deterministic gate code).
- **ADR-0009 (Firecracker host-side nftables):** adds `firecracker/network_policy.py` as the 4th subprocess chokepoint (the original 3 in arch §Tool-use safety predate this ADR; the 4-file allowlist this story pins is the post-ADR-0009 source-of-truth).
- **ADR-0012 (static env allowlist):** the `env_allowlist.filter` belt-and-suspenders property — deny-substring rejection survives even if a key is added to ALLOWLIST. The schema fence test must exercise this monkeypatched property, not only the trivial "absent from allowlist anyway" case.
- **ADR-0013 (digest-pinned policy YAML):** `tools/digests.yaml#sandbox.policy_yaml` is mandatory at startup — presence enforcement here, value enforcement in S6-03.
- **ADR-0014 (`ObjectiveSignals` extra=forbid + static introspection):** this story ships the schema-tier substring-screen fence that survives even if `tests/sandbox/test_objective_signals_introspection.py` (S1-03) is deleted. **Must import the canonical `iter_nested_field_names` from `sandbox.signals._introspection`** — not re-declare the walker (re-declaration silently forks the trust anchor).
- **ADR-0001 (two-chokepoint sandbox seam):** the Stage 6 chokepoint placeholder is the structural floor; S5-04 ships the full AST walk once `gates/runner.py` exists as a legitimate caller.
- **CLAUDE.md "Match existing convention":** `tests/fence/test_no_llm_in_transforms.py` (runtime-closure walker with planted-positive subprocess companion) and `tests/fence/test_lint_imports_catches_planted_leak.py` (`pytest.fail` over `skip`, CODEOWNERS social anchor) are the precedent patterns. S1-07 mirrors the planted-positive idiom (in-test AST string, no committed planted files) and the "fail loud, no skip" rule.
- **CLAUDE.md "Extension by addition":** Phase 7's eventual `test_no_pip_in_distroless_layer.py` lands under `tests/schema/` by adding a new file; the `_BANNED_LLM_IMPORTS` Final tuple in this story's `test_no_llm_imports_in_sandbox.py` is extended *only* via test-file edit + Phase-7-arch amendment (not via auto-discovery of a separate config file).
- **CLAUDE.md "Surface conflicts, don't average them":** the 3-vs-4 subprocess-chokepoint count drift inside the draft is resolved explicitly (4 per ADR-0009; arch §Tool-use safety predates ADR-0009 and is amended).
- **CLAUDE.md "Tests verify intent, not just behavior":** every fence test must have an **in-test planted-positive** that proves the walker would fire — otherwise the test verifies "walker walks an empty list" instead of "walker detects the offense."

### Open ambiguities (resolved before Stage 2)

- **`_iter_nested_field_names` (draft) vs `iter_nested_field_names` (S1-03 reality).** Resolution: rewrite to `from codegenie.sandbox.signals._introspection import iter_nested_field_names`; call type-driven on `ObjectiveSignals`.
- **3 chokepoints (draft AC) vs 4 (draft code block).** Resolution: 4, per ADR-0009; the arch §Tool-use safety bullet predates ADR-0009 and is silently amended by the ADR's acceptance.
- **Banned LLM set narrow (Phase 5 sandbox/gates) vs `FORBIDDEN_LLM_SDKS` (gather-pipeline).** Resolution: keep narrow per arch; document the scope divergence in module docstring; AC-LL-2 pins byte-equality with arch.
- **Walker abstraction (extract `_walkers.py` vs inline).** Resolution: extract — 6 callers on day one clears rule-of-three; future Phase 7 adds more; introduction-time extract is cheaper.

### Phase 0/3/5 prior art consulted

- [`tests/fence/test_no_llm_in_transforms.py`](../../../../../tests/fence/test_no_llm_in_transforms.py) — Phase 3 — runtime-closure walker with planted-positive subprocess companion; the "mutation-resistance via shared scanner" idiom S1-07 mirrors (statically, via in-test AST strings).
- [`tests/fence/test_lint_imports_catches_planted_leak.py`](../../../../../tests/fence/test_lint_imports_catches_planted_leak.py) — Phase 3 — planted-positive subprocess pattern with `pytest.fail` over `skip` and CODEOWNERS framing. S1-07 inherits the "no skip / no xfail" discipline.
- [`tests/unit/test_pyproject_fence.py`](../../../../../tests/unit/test_pyproject_fence.py) — Phase 0 — `EXPECTED_FORBIDDEN_SET = frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})` and sync test asserting `FORBIDDEN_LLM_SDKS == EXPECTED_FORBIDDEN_SET`. Precedent for the byte-equality drift-fence pattern; S1-07's `_BANNED_LLM_IMPORTS` sync AC mirrors this.
- S1-02 HARDENED report — `SandboxSpec.env: Mapping[str, str]` shape that `env_allowlist.filter`'s output must conform to.
- S1-03 HARDENED report — pins `iter_nested_field_names` (no underscore) in `sandbox.signals._introspection`; pins `__all__` excludes `_iter_nested_field_names` from `models.py`. The load-bearing consistency check.
- S1-05 HARDENED report — pins `env_allowlist.filter` signature `(Mapping[str, str]) -> dict[str, str]`, the `ALLOWLIST` / `ALLOWLIST_PREFIXES` / `DENY_SUBSTRINGS` constants, and AC-DN-2 ("Deny applies BEFORE allow"). S1-07 inherits the deny-applies-before-allow property and adds the monkeypatch-into-allowlist fence.
- S1-06 HARDENED report — establishes the "fence test cites ADR in module docstring + `__all__` exact + ban `yaml.load`" module-purity pattern. S1-07 carries forward at the test-file level via `tests/schema/test_schema_fence_purity.py`.

## Critic findings (Stage 2)

### Critic A — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| A-1 | block | `_iter_nested_field_names` from `sandbox.signals.models` does not exist — S1-03 ships `iter_nested_field_names` in `_introspection` | AC-OS-1 / AC-OS-2 rewrite import + type-driven invocation |
| A-2 | block | 3-vs-4 subprocess-chokepoint count drift inside the story (AC says 3, code says 4) | AC-SP-1 pins 4 per ADR-0009; AC text + code block aligned |
| A-3 | block | `tests/schema/__init__.py` has no AC | AC-IN-1 (empty package marker, mirrors `tests/fence/__init__.py`) |
| A-4 | block | `test_stage6_chokepoint.py` vacuous on Step 1; no positive control | AC-S6-1..AC-S6-4 + planted-positive (`"validation.run_x()"` in-test AST string) |
| A-5 | block | `tools/digests.yaml` root shape unconstrained (list/None/str round-trips → opaque `TypeError`) | AC-DG-3 / AC-DG-4 (root must be `dict`; `sandbox` value must be `dict`) |
| A-6 | block | `test_env_allowlist_no_credentials.py` doesn't exercise ADR-0012 belt-and-suspenders (monkeypatch ALLOWLIST + re-assert) | AC-EA-3 + paired monkeypatch test |
| A-7 | harden | `_BANNED` set divergence vs `FORBIDDEN_LLM_SDKS` unexplained; future contributor may "fix" via import | AC-LL-2 byte-equality + module-docstring scope rationale |
| A-8 | harden | AST walk catches only `Import` / `ImportFrom`; misses `importlib.import_module(...)` / `__import__(...)` | Pinned in module docstring + AC-LL-3 (static-import-only scope) |
| A-9 | harden | `Path` membership comparison brittle on macOS / symlinks | AC-SP-3 (both sides compared via `path.relative_to(ROOT)`) |
| A-10 | harden | `test_digests_yaml.py` value shape too loose ("any non-empty str") | AC-DG-5 / AC-DG-6 (placeholder = `"TBD"` exact OR 64-char hex; ban partial-real partial-TBD) |
| A-11 | harden | `Depends on` understated | Widen to `S1-02, S1-03, S1-05, S1-06` |
| A-12 | harden | ADR-0009 missing from `ADRs honored` | Add ADR-0009 |
| A-13 | harden | Per-test < 1 s runtime in Refactor only | Promote to AC-PG-3 |
| A-14 | nit | `tests/schema/__init__.py` semantics (empty package marker) implicit | AC-IN-1 (empty) |

### Critic B — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| B-1 | block | Zero mutation-resistance — every fence walker vacuously passes on Step 1 | AC-PP-1..AC-PP-6 — every fence test ships an in-test planted-positive companion (in-memory AST string; no committed planted file) |
| B-2 | block | `test_no_llm_imports_in_sandbox.py` planted-positive missing | AC-PP-1 + `test_walker_detects_planted_anthropic_import` (synthetic AST string) |
| B-3 | block | `test_no_subprocess_outside_build_chokepoint.py` planted-positive missing | AC-PP-2 + `test_walker_detects_planted_subprocess_import` |
| B-4 | block | `test_objective_signals_static.py` planted-positive missing — also still imports the wrong symbol | AC-PP-3 + `test_walker_detects_planted_forbidden_field` (in-test `_Planted(BaseModel)` with `confidence: int = 0`) |
| B-5 | block | `test_env_allowlist_no_credentials.py` belt-and-suspenders property not tested | AC-EA-3 monkeypatch + `test_deny_substring_survives_allowlist_addition` |
| B-6 | block | `test_stage6_chokepoint.py` planted-positive missing | AC-PP-5 + `test_walker_detects_planted_validation_call` |
| B-7 | harden | `test_digests_yaml.py` no round-trip / no value-shape check | AC-PP-6 + AC-DG-5..AC-DG-6 |
| B-8 | harden | Test-file purity (mirroring S1-02..S1-06 `test_*_purity.py`) missing | AC-PU-1 + `tests/schema/test_schema_fence_purity.py` (AST scan of every `test_*.py` in `tests/schema/`) |
| B-9 | harden | No "no skip / no xfail" AC mirroring `tests/fence/` discipline | AC-QG-3 |

### Critic C — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| C-1 | block | Wrong import path for the substring walker (`_iter_nested_field_names` vs `iter_nested_field_names`); wrong module (`models.py` vs `_introspection.py`) | AC-OS-1 (re-import path) + AC-OS-2 (type-driven call signature `iter_nested_field_names(ObjectiveSignals)`) |
| C-2 | block | Subprocess-chokepoint count drift between draft AC (3) and draft code (4) — ADR-0009 is the resolution | AC-SP-1 pins 4; ADR-0009 added to `ADRs honored`; Notes documents the count growth |
| C-3 | harden | `_BANNED` set differs from `FORBIDDEN_LLM_SDKS` without explanation | Module docstring + AC-LL-2 sync check |
| C-4 | harden | Module-purity test (mirror S1-02..S1-06 `test_*_purity.py`) missing | AC-PU-1 + `tests/schema/test_schema_fence_purity.py` |
| C-5 | harden | Coverage / quality-gate AC drift vs prior Step-1 stories | AC-QG-1..AC-QG-4 (ruff / mypy / pytest / no-skip — explicit bullets) |
| C-6 | harden | `Depends on` understated | Widen to `S1-02, S1-03, S1-05, S1-06` |
| C-7 | harden | ADR-0009 missing from honored ADRs | Add ADR-0009 |

### Critic D — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| D-1 | harden | `ROOT` + `_iter_py` + `ast.parse(...)` repeated across 6 fence tests — rule-of-three cleared on day one (6 callers); extract at introduction is cheaper than refactor-on-3rd-additional-file | New `tests/schema/_walkers.py` with `ROOT: Final[Path]`, `iter_py(*roots)`, `iter_top_level_imports(path)`; AC-W-1..AC-W-3 |
| D-2 | harden | Fence-test bodies should be thin "compose walker + assert" Strategy implementations over the `_walkers.py` kernel | Pinned in TDD plan — each fence test imports from `tests.schema._walkers` and applies its own predicate |
| D-3 | harden | `_BANNED_LLM_IMPORTS` as `Final[frozenset[str]]` (extension-by-addition: Phase 7 adds via test-file edit) | AC-LL-1 |
| D-4 | harden | Test-file purity invariant (closed import set; fence-test files must not import from the modules they police) | AC-PU-1 |
| D-5 | nit | `_BLAKE3_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")` constant for re-use when S6-03 lands value validation | Recorded in Notes — NOT for S1-07 (S6-03 owns the value-shape upgrade) |
| D-6 | nit | Substring-deny matrix duplication with `tests/sandbox/test_env_allowlist.py` (S1-05) — schema-tier purpose is to survive S1-05 deletion | Keep duplicate; documented in Notes |

## Conflict resolution

- **C-1 / C-3 (use `iter_nested_field_names` from `_introspection`) vs draft body literal:** Consistency wins — the draft body is structurally broken (would `ImportError`); rewrite is non-negotiable.
- **A-2 / C-2 (3 vs 4 subprocess chokepoints):** ADR-0009 wins — it was accepted after the original 3-file decision and adds the 4th. The arch §Tool-use safety bullet (which still says 3) is silently amended by ADR-0009's acceptance; this story's AC text serves as the post-ADR-0009 source-of-truth and Notes documents the growth.
- **B-1..B-6 (planted-positive tests) vs Rule 2 (Simplicity First):** Adding ~5 LOC per fence test for an in-memory AST string check is well-spent simplicity cost — without it, every test is silently-vacuous on Step 1 and Rule 9 ("tests verify intent, not just behavior") fails outright. Planted-positives are *the* idiom in this codebase's `tests/fence/` precedent.
- **D-1 (extract `_walkers.py`) vs Rule 3 (Surgical changes):** Extract is in-scope because this story introduces `tests/schema/` as a new namespace; getting the helper module right at introduction is cheaper than refactoring after 4+ siblings already inline. Rule-of-three is cleared on day one (6 callers).
- **A-8 (AST walk misses `importlib.import_module`) vs Rule 2:** Document the limitation; do not over-engineer. The runtime defense lives in chokepoint discipline and the import-linter contracts, not this static fence.

## Edits applied to the story

1. **Status** flipped from `Ready` to `HARDENED`.
2. **Depends on** widened from `S1-05, S1-06` to `S1-02, S1-03, S1-05, S1-06`.
3. **ADRs honored** widened from `ADR-0014, ADR-0012, ADR-0013, ADR-0008, ADR-0001` to add **ADR-0009** (Firecracker host-side nftables — 4th subprocess chokepoint).
4. **Validation notes** block appended directly under the story header documenting all 17 findings and resolutions with the verdict.
5. **Context** paragraph extended with: (a) explicit "schema-tier survives deletion of sandbox-tier" rationale, (b) "planted-positive companion" terminology, (c) `_BANNED_LLM_IMPORTS` divergence-from-`FORBIDDEN_LLM_SDKS` note.
6. **References — where to look** extended with:
   - Phase ADRs section: added ADR-0009.
   - New "Prior validated stories carried forward" bullet (S1-02 / S1-03 / S1-05 / S1-06).
   - New "Codebase precedents" bullet (`tests/fence/test_no_llm_in_transforms.py`, `tests/fence/test_lint_imports_catches_planted_leak.py`, `tests/unit/test_pyproject_fence.py`).
7. **Goal** sentence rewritten to make explicit: shared `_walkers.py` kernel, planted-positive companions, test-file purity AC, `_BANNED_LLM_IMPORTS` Final tuple, post-ADR-0009 4-chokepoint allowlist.
8. **Acceptance criteria** rewritten from ~10 prose bullets to ~40 individually-verifiable ACs organized into 10 lettered sections (W: walkers kernel; IN: `__init__.py` marker; LL: LLM-import deny; SP: subprocess allowlist; OS: ObjectiveSignals substring screen; EA: env allowlist; S6: Stage 6 chokepoint placeholder; DG: digests YAML; PP: planted-positive companions; PU: test-file purity; QG/PG: quality gates).
9. **Schema fence design notes** new section added — explains the `_walkers.py` kernel + Strategy-per-fence-test composition + the "schema-tier survives sandbox-tier deletion" rationale + the divergent-deny-set rationale.
10. **Implementation outline** rewritten with explicit step-by-step ordering: `__init__.py` first, `_walkers.py` second, six fence tests third (each with its planted-positive companion), test-file purity fence fourth, `tools/digests.yaml` fifth.
11. **TDD plan** rewritten from 6 test files (~150 LOC sketch with broken import + 3/4 inconsistency + zero planted-positives) to 8 test files (~480 LOC sketch with):
    - corrected `iter_nested_field_names` import from `sandbox.signals._introspection`;
    - 4-chokepoint allowlist using `path.relative_to(ROOT)` comparison;
    - `_BANNED_LLM_IMPORTS: Final[frozenset[str]]` module-level constant;
    - planted-positive companion test for every fence (six tests, each parsing an in-memory synthetic AST string);
    - `monkeypatch`-into-allowlist test for env-allowlist (ADR-0012 belt-and-suspenders);
    - `test_schema_fence_purity.py` AST-walks every `tests/schema/test_*.py` and pins the import set;
    - `tools/digests.yaml` root-must-be-dict + `sandbox` value-must-be-dict + value-must-be-`"TBD"`-or-64-hex.
12. **Files to touch** expanded from 8 to 10 entries: added `tests/schema/_walkers.py` (new kernel), `tests/schema/test_schema_fence_purity.py` (new module-purity fence).
13. **Out of scope** widened to explicitly defer: full ImportFrom + aliased-import walk for Stage 6 chokepoint (S5-04); BLAKE3 digest value validation (S6-03); runtime-import fences for `importlib.import_module(...)` (intentionally deferred — not assigned to any story).
14. **Notes for the implementer** rewritten with:
    - the `iter_nested_field_names` import path correction (and why re-declaring locally is forbidden);
    - the 4-chokepoint count + ADR-0009 reference;
    - the `_BANNED_LLM_IMPORTS` divergent-scope explanation vs `FORBIDDEN_LLM_SDKS`;
    - the planted-positive idiom + in-memory AST string convention (no committed planted files);
    - `Path.relative_to(ROOT)` comparison + macOS case-insensitivity caveat;
    - `_walkers.py` kernel as the ONLY shared helper (per-test predicates stay inline);
    - `_BLAKE3_DIGEST_RE` constant deferred to S6-03;
    - "no skip / no xfail" discipline matching `tests/fence/`;
    - per-test < 1 s budget — the schema fence is the PR critical path floor.

## Files written by this validation pass

- `docs/phases/05-sandbox-trust-gates/stories/S1-07-ci-fence-tests-digests-yaml.md` (edited in place — `Status: HARDENED`, validation notes block + tightened ACs + 8-test-file TDD plan with planted-positive companions)
- `docs/phases/05-sandbox-trust-gates/stories/_validation/S1-07-ci-fence-tests-digests-yaml.md` (this file)

## Verdict

**HARDENED** — Six block-tier weaknesses resolved (wrong import path, 3-vs-4 chokepoint drift, vacuous-walker mutation gap, ADR-0012 belt-and-suspenders not exercised, Stage 6 placeholder doubly-vacuous, `tools/digests.yaml` root shape unconstrained). Eleven harden-tier improvements applied. No `RESCUE`-tier structural problems. Story is ready for `phase-story-executor`.
