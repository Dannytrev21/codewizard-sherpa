# Validation report: S5-04 — Stage 6 chokepoint AST test + orchestrator wiring

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S5-04 promotes the S1-07 stub `tests/schema/test_stage6_chokepoint.py` to a real AST walker that fails loud if any module under `src/codegenie/` reaches the Stage-6 Validate entrypoint outside an allowlisted call-site, and (in the draft) wires Phase 3's orchestrator to call `GateRunner.run` at the Stage-6 site. The intent — a single load-bearing structural fence that enforces ADR-0001's "two-chokepoint sandbox seam" at lint time — is sound. But the draft was written against an architectural model that the actual Phase-3 codebase superseded, and the walker is silently vacuous on Step-1 because no qualifying call-sites exist yet.

| Draft assumption | Reality on `master` |
|---|---|
| Phase-3 Stage 6 lives in a `src/codegenie/validation/` package; the walker polices `from codegenie.validation import …`, `import codegenie.validation`, and `validation.<attr>` attribute access | There is no `codegenie.validation` package and never was. The canonical Phase-3 Stage-6 entrypoint is `codegenie.transforms.trust_scorer.TrustScorer.score()` (`src/codegenie/transforms/trust_scorer.py`, S6-02 GREEN 2026-05). S6-03 (subgraph node Protocol, GREEN) and the S6-02 alias `StageOutcome` (line 69 of `trust_scorer.py` — `"ADR-0015/S6-04 Phase-5 name for the Stage-6 validation return type"`) cement the surface. A regex over `r"\bcodegenie\.validation\.\w+"` matches **nothing in the entire repo**, today and forever — buggy walker and correct walker are indistinguishable. |
| `src/codegenie/orchestrator/remediation.py` exists and the story refactors its direct `validation.*` call to `GateRunner(...).run(GateContext(...))` | There is no `src/codegenie/orchestrator/` package on `master`. The `RemediationOrchestrator` is Phase-3 story `S6-04-remediation-orchestrator`, currently **BLOCKED** awaiting a `/phase-story-validator` re-harden against [Phase-3 ADR-0015](../../../03-vuln-deterministic-recipe/ADRs/0015-orchestrator-self-loads-repo-context-and-resolves-cve.md). An executor following the draft literally cannot edit a file that does not exist; an attempt at "creating" `src/codegenie/orchestrator/remediation.py` from this story would fork a kernel S6-04 is the rightful home of. |
| `Depends on: S5-02` is the complete picture | Real upstream surface: **S1-07** (the chokepoint *stub* + the `tests/schema/` directory + the prospective `tests/schema/_walkers.py` kernel — S1-07 is HARDENED, **not yet GREEN**); **S5-02** (`gates/runner.py` and `GateRunner.run` — HARDENED, not yet GREEN); **Phase-3 S6-04** (the orchestrator that actually does the call-site swap — BLOCKED). On the current `master`, none of S5-04's three allowlisted callers exist; the draft would commit a fence whose own scope is empty. |
| The walker catches all Python shapes that reach the Stage-6 entrypoint | Story Refactor § acknowledges aliased imports as a gap and *defers a decision*. `__import__("…")`, `getattr(__import__(…), …)`, and re-exports through `transforms/__init__.py` are not addressed. Worse, the `visit_Attribute` arm treats *any* identifier named `validation` as a hit regardless of binding — a function parameter `def f(validation): validation.something` would produce false positives the moment a real callsite arrives. |
| `Path` membership against `SRC.rglob("*.py")` works reliably | macOS' case-insensitive default filesystem + symlinked checkouts (CI worktrees, `pyenv`, `direnv`) yield differing absolute paths for the same file. Refactor § mentions `.resolve()` but doesn't promote to AC; without normalization the allowlist silently fails open and the fence rubber-stamps a real leak. |
| One inline adversarial sub-test (`from codegenie.validation import run_validation`) is sufficient | A single fixture only exercises one of the four shapes the walker claims to catch (`from-import`, `import-name`, `import-as`, `importlib.import_module`). A regression that breaks any of the other three is silently invisible — the test is **mutation-passing under the trivial case**. |
| The story owns both the test promotion and the orchestrator wiring | The orchestrator wiring touches a module that lives in Phase-3 and is currently BLOCKED. The test promotion can land independently and ship a useful structural fence the moment any future caller appears. Bundling the two forces this story to wait on S6-04 / forces S6-04 to import this story's call-site shape. **Splitting the AC (test-promotion now, wiring deferred to S6-04 GREEN) is the cheaper-to-reverse direction.** |

The validator's response: **re-target the walker to the canonical Stage-6 entrypoint (`codegenie.transforms.trust_scorer.TrustScorer.score`) plus the S6-02 alias (`codegenie.transforms.trust_scorer.StageOutcome`); pin the allowlist to the only two legitimate-caller modules that the architecture *names* — `src/codegenie/gates/runner.py` (S5-02) and the Phase-3 orchestrator module S6-04 lands — and treat the allowlist's *populated state* as the gate (the walker still passes vacuously on Step-1 but the planted-positive guarantees mutation-resistance); split the orchestrator wiring off this story (defer to S6-04, with a Notes paragraph for the implementer of whichever story lands second); harden the walker against aliased imports, `importlib.import_module`, `__import__`, attribute false-positives, and case-insensitive / symlinked paths; ship an in-memory planted-positive parametrized across all five shapes; and consume the `tests/schema/_walkers.py` kernel (S1-07) rather than re-declaring `_Walker` inline.**

The remaining slice — what S5-04 actually owns:

1. A real `tests/schema/test_stage6_chokepoint.py` AST walker that polices imports + attribute access against the canonical Stage-6 entrypoint module, with allowlist-by-relative-path against the **two** modules ADR-0001 names.
2. An in-memory planted-positive companion that parametrizes across five Python import / attribute shapes — `from … import`, `import …`, `import … as …` + attribute use, `importlib.import_module("…")`, `__import__("…")` — and asserts the walker emits the offending file path + line number for each.
3. Consumption of the `tests/schema/_walkers.py` kernel (`iter_py`, `iter_top_level_imports`) S1-07 ships; no inline re-declaration.
4. Path normalization (`path.resolve().relative_to(REPO_ROOT)`) that survives macOS case-insensitive FS + symlinked checkouts.
5. A `Notes for implementer` paragraph naming the rule-of-three opportunity to extract a `make_namespace_chokepoint_walker(forbidden_prefix, allowlist)` helper to the kernel once a fourth namespace-chokepoint test arrives (today's three: no-llm, no-subprocess-outside-build, and this one — Rule-2 simplicity still wins until #4 lands).
6. An explicit `Depends on:` widening to S1-07 + S5-02; a structural NOTE that the orchestrator-wiring AC is deferred to Phase-3 S6-04 GREEN — neither story is the right home for both halves.

No `RESCUE`-tier escalation: the goal text needed only minor surface edits (drop `validation.*` namespace wording; promote `transforms.trust_scorer.TrustScorer.score`); the acceptance criteria, the implementation outline, and the TDD plan were rewritten in place to bind to the actual Phase-3 surface. **Stage 3 (research) was skipped — every gap was answerable from in-repo precedents (`tests/fence/test_no_llm_in_transforms.py` for the planted-positive idiom + S1-07's HARDENED report for the `_walkers.py` kernel shape) and the four prior HARDENED phase-5 reports.**

## Findings by critic

### Coverage critic (10 findings: 4 block, 5 harden, 1 nit)

#### Block-tier

1. **(coverage — block) Walker scope is empty on Step-1.** The story's regex `r"\bcodegenie\.validation\.\w+"` and `module.startswith("codegenie.validation")` match nothing because that package does not exist. A buggy walker (e.g., `return []` at the top of `_walk`) is indistinguishable from a correct one. **Fix:** AC-PP-1 — every walker check is paired with an in-memory planted-positive that constructs a synthetic `ast.parse(source_string)` and asserts the walker emits a non-empty offender list naming the planted symbol. AC-PP-2 — the planted-positive is parametrized across all five shapes the walker claims to catch.

2. **(coverage — block) Namespace mismatch — wrong target.** Story polices `codegenie.validation.*`. Canonical Phase-3 Stage-6 entrypoint is `codegenie.transforms.trust_scorer.TrustScorer.score` (S6-02 GREEN). **Fix:** AC-TARGET-1 — the forbidden-prefix tuple is `("codegenie.transforms.trust_scorer",)` + the S6-02 re-exported alias `StageOutcome` is policed only by its qualified import path, not by its name (StageOutcome is consumed by *every* Phase-5 gate result reader; the chokepoint is on the **score** call, not the **type**). AC-TARGET-2 — the allowlist is `frozenset({"src/codegenie/gates/runner.py", "<orchestrator-module-from-S6-04>"})`, with the second entry held as a `Final` placeholder constant + a TODO comment naming Phase-3 S6-04.

3. **(coverage — block) Walker misses three out of five Python import shapes.** Story TDD code handles `from codegenie.validation import …`, `import codegenie.validation`, and `importlib.import_module("codegenie.validation.…")`. It misses: (a) `import codegenie.transforms.trust_scorer as ts` + `ts.TrustScorer().score(...)` (binds an alias, escapes the name check); (b) `__import__("codegenie.transforms.trust_scorer")` (dynamic, not a `Call` to `Attribute` of `import_module`); (c) re-exports through `codegenie.transforms.__init__` (the walker scans only literal namespace prefixes, not transitively-aliased re-exports). **Fix:** AC-SHAPE-1 — the walker catches `Import.alias.name`, `Import.alias.asname` (when present), `ImportFrom.module`, `Call(func=Attribute(attr="import_module"))`, AND `Call(func=Name(id="__import__"))` with a literal arg; the per-shape planted-positive (AC-PP-2) is the mutation guard.

4. **(coverage — block) Orchestrator-wiring AC depends on a BLOCKED upstream story.** AC-5 (refactor `RemediationOrchestrator.validation.* → GateRunner.run`) references `src/codegenie/orchestrator/remediation.py` which does not exist on `master` and is owned by Phase-3 S6-04 (BLOCKED). **Fix:** AC-SPLIT-1 — S5-04 ships ONLY the chokepoint test promotion. The orchestrator wiring is deferred to Phase-3 S6-04 (the story that constructs the orchestrator) with a Notes paragraph telling whichever-story-lands-second to update the allowlist constant + add the GateRunner call-site. The "Surfaces a pre-existing caller" AC is reframed as: "the walker, run on the current Step-N codebase, must find zero offenders OR every offender names a future allowlisted module — surfaced offenders escalate via ADR amendment, not silent allowlist edit."

#### Harden-tier

5. **(coverage — harden) `visit_Attribute` false-positive on unbound `validation` name.** Story walker treats any `Attribute(value=Name("validation"))` as a hit. A function parameter `def f(validation): ...` would false-positive. **Fix:** AC-BIND-1 — `visit_Attribute` is **dropped** from the walker; the chokepoint *is* the import, and an aliased reference still has to import first. Document the limitation in the walker docstring. Simpler walker > brittle scope tracking.

6. **(coverage — harden) Path comparisons brittle on case-insensitive FS + symlinks.** Story Refactor § mentions `.resolve()` but doesn't pin it. **Fix:** AC-PATH-1 — every path comparison reduces to `path.resolve().relative_to(REPO_ROOT)`; allowlist is declared as relative-path strings (`"src/codegenie/gates/runner.py"`), compared via `str(path.resolve().relative_to(REPO_ROOT))`. Adversarial sub-test uses `tmp_path` with a symlink to verify normalization.

7. **(coverage — harden) `Depends on:` understated.** Story says `S5-02`. Real dependencies: **S1-07** (stub + `tests/schema/` package + `_walkers.py` kernel — HARDENED, not GREEN); **S5-02** (`gates/runner.py` — HARDENED, not GREEN); cross-phase **Phase-3 S6-04** (the orchestrator that owns the second allowlisted call-site — BLOCKED). **Fix:** `Depends on: S1-07 (tests/schema/ + _walkers.py kernel), S5-02 (gates/runner.py). Cross-phase: Phase-3 S6-04 (the second allowlisted call-site lands there, NOT in this story).` Explicit BLOCKED-on-cross-phase note in the Status line is optional but recommended.

8. **(coverage — harden) ADRs honored too narrow.** Story cites ADR-0001 only. Phase-5 ADR-0006 (Protocol vs ABC convention) shapes the `SubgraphNode` Protocol per S6-03 and is contextually relevant. Phase-3 ADR-0015 (`/03-vuln-deterministic-recipe/ADRs/0015-orchestrator-self-loads-repo-context-and-resolves-cve.md`) is the cross-phase resolution that defines what the orchestrator module *is*. **Fix:** widen to `ADR-0001, ADR-0006`; cite Phase-3 ADR-0015 as cross-phase context in the References section.

9. **(coverage — harden) Walker pass-time gate per arch §Testing strategy.** Story has `≤ 1 s on a clean checkout`. **Fix:** AC-PG-1 promoted from prose to AC + a sub-test that asserts `pytest --no-cov tests/schema/test_stage6_chokepoint.py` total runtime is < 1 s using `pytest`'s `--durations` programmatic check (or a simpler `time.perf_counter` wrap in the test).

#### Nit

10. **(coverage — nit) Pin the docstring + ADR citation in the test file.** Story Refactor § says "Add a module docstring on the test file citing ADR-0001 and §Goal 1." **Fix:** promote to AC-DOC-1 (verified by a sub-test that the test file's module docstring contains the substring `"ADR-0001"`).

### Test-quality critic (8 findings: 3 block, 4 harden, 1 nit)

#### Block-tier

11. **(test-quality — block) Single-fixture adversarial test.** TDD `test_walker_detects_forbidden_caller_fixture` exercises one Python shape. Mutation-passing: a walker that handles only `from …` and silently drops `import … as …` cases passes. **Fix:** AC-PP-2 — `@pytest.mark.parametrize` over the five shapes (`from-import`, `import-name`, `import-as`, `importlib.import_module`, `__import__`), each constructed inline via `tmp_path.write_text(...)`; each parametrized case asserts the walker emits ≥1 offender naming both the file path and the line number of the planted statement.

12. **(test-quality — block) No mutation-resistance for the "passes on Step-1" branch.** The main test (`test_only_allowlisted_modules_reach_validation_namespace`) only checks that offenders is empty. A walker that *always* returns empty (regression) passes. **Fix:** AC-MUT-1 — the same `_walk` callable used by the main test is also called by the planted-positive sub-tests; a regression that empties `_walk` kills the planted-positive AND the live test (parity-with-Phase-0 `tests/fence/test_no_llm_in_transforms.py` precedent).

13. **(test-quality — block) Walker name not pinned at module scope.** Story TDD declares `_Walker` and `_walk` as private — fine — but tests import them only by leaning on `tests/schema/test_stage6_chokepoint.py`'s own internals. When the `_walkers.py` kernel arrives (S1-07), the walker primitive belongs there, not inline. **Fix:** AC-KERNEL-1 — the test consumes `from tests.schema._walkers import iter_py, iter_top_level_imports`; the per-test logic is the composition (filter to forbidden prefix + check allowlist), not the walking. If S1-07 has not yet GREEN-shipped when this story executes, the executor escalates (story is BLOCKED-on-S1-07) — does NOT re-declare the kernel inline.

#### Harden-tier

14. **(test-quality — harden) Test message on failure not byte-tested.** AC-7 says the failure message must contain `{path}:{lineno} -> {symbol}` but no sub-test exercises a forced-failure path. **Fix:** AC-MSG-1 — a sub-test invokes `_walk` against a synthetic `from codegenie.transforms.trust_scorer import TrustScorer` planted under `tmp_path / "src" / "codegenie" / "_planted_caller.py"` (or directly via `_walk` on an in-memory `ast.parse`), and asserts the offender string matches the regex `r"^\S+:\d+ -> from codegenie\.transforms\.trust_scorer import \w+$"`.

15. **(test-quality — harden) `tests/schema/__init__.py` package-marker invariant unenforced.** S1-07 ships the package marker. This story's tests live under it; a regression that deletes the package marker silently breaks pytest discovery. **Fix:** AC-PKG-1 — a sub-test asserts `(REPO_ROOT / "tests" / "schema" / "__init__.py").is_file()` and is empty (mirrors `tests/fence/__init__.py` convention).

16. **(test-quality — harden) Hypothesis property absent — namespace prefix generalization.** The walker claims to catch any `codegenie.transforms.trust_scorer.*` import; an executor might hand-roll a per-symbol check (`if alias.name == "codegenie.transforms.trust_scorer.TrustScorer"`) that breaks on `codegenie.transforms.trust_scorer.StageOutcome` or future submodules. **Fix:** AC-PROP-1 — one Hypothesis property: for any text matching `r"^codegenie\.transforms\.trust_scorer(\.[a-zA-Z_][a-zA-Z0-9_]*)*$"`, the walker flags the synthetic `from <text> import x` import. 50 examples; runs in < 200 ms. Document as a metamorphic property: the walker's verdict on `prefix` equals its verdict on `prefix.suffix` for any valid `suffix`.

17. **(test-quality — harden) Per-test runtime AC unenforced.** AC says ≤ 1 s but no test asserts it. **Fix:** AC-PG-1 (above) covers this.

#### Nit

18. **(test-quality — nit) `pytest --no-cov` requirement undocumented in AC.** Story Notes mentions it; promote to a literal AC sub-bullet under AC-PG-1 so an executor running `pytest tests/schema/` doesn't get tripped by `--cov-fail-under=85`.

### Consistency critic (7 findings: 3 block, 3 harden, 1 nit)

#### Block-tier

19. **(consistency — block) `codegenie.validation` is not in the codebase.** See finding 2. The arch design's S5-04 row (§Testing strategy line 913) text reads `validation.*` but the **actual call-site** as of S6-02 GREEN is `codegenie.transforms.trust_scorer.TrustScorer.score()`. The arch text is a historical artifact pre-S6-02. The validator's source-of-truth precedence (Consistency > Coverage > Test-Quality > Design-Patterns) resolves this in favor of the **shipped code** (S6-02 GREEN > arch design draft). The story is re-targeted; arch §Testing strategy gets a follow-up amendment via S8-04 (ADR audit + roadmap exit criteria) — not this story's surface.

20. **(consistency — block) `src/codegenie/orchestrator/remediation.py` is unowned by this phase.** Phase-3 S6-04 owns it; cross-phase edits are extension-by-edit (CLAUDE.md load-bearing commitment forbids). **Fix:** AC-SPLIT-1 (above) splits the orchestrator-wiring half off; the Notes paragraph documents the handoff to S6-04.

21. **(consistency — block) Cross-phase BLOCKED dependency unflagged.** S6-04 (BLOCKED) is the home of the second allowlisted call-site. The story cannot achieve "all callsites allowlisted with no `# TODO`" until S6-04 GREENs. **Fix:** Status line updated to `Ready (HARDENED 2026-05-25; cross-phase BLOCKED on Phase-3 S6-04 for the orchestrator allowlist row — see References)`; Files-to-touch flagged accordingly.

#### Harden-tier

22. **(consistency — harden) S6-02 alias `StageOutcome` underspecified in the walker target.** The arch describes "`validation.*`" but the canonical surface is the **method call** `TrustScorer.score()`, not the type. Importing the `TrustOutcome` / `StageOutcome` type is fine (every gate reader needs it); only the `TrustScorer` *class* + `.score()` call is the chokepoint. **Fix:** AC-TARGET-1 (above) restricts the forbidden prefix to `codegenie.transforms.trust_scorer.TrustScorer` (the class) + documents that imports of the **type aliases** `TrustOutcome` / `StageOutcome` are not the chokepoint (a Notes paragraph explains the asymmetry).

23. **(consistency — harden) Phase-3 ADR-0015 cross-phase relation absent.** ADR-0015 (orchestrator self-loads repo context + resolves CVE) is what unblocks S6-04 and is what gives the orchestrator module a defined shape. **Fix:** References — add link to Phase-3 ADR-0015 under "Cross-phase context".

24. **(consistency — harden) `tests/schema/_walkers.py` kernel ownership cited.** S1-07's HARDENED report (§Validation-notes finding 14, design-patterns) names `tests/schema/_walkers.py` as the day-1 extraction with six callers. S5-04 is the **seventh** caller. **Fix:** Notes-for-implementer + References cite S1-07 as the kernel's owner; this story consumes, does not extend.

#### Nit

25. **(consistency — nit) Refactor § "verify the walker handles aliased imports … if the codebase uses this pattern, add a `visit_Attribute` check …" is the wrong policy.** Refactor § conditionally adds a brittle scope-aware check. Real policy: the chokepoint is the import; AC-SHAPE-1 (above) catches aliased imports at the `Import.alias.asname` level. The `visit_Attribute` arm is **dropped** (finding 5). **Fix:** Refactor § rewritten to match the kernel-consumption pattern.

### Design-patterns critic (6 findings: 1 block, 4 harden, 1 nit)

#### Block-tier

26. **(design-patterns — block) Inline `_Walker` re-declares logic that belongs to the `_walkers.py` kernel.** S1-07's day-1 extraction (finding 14 of its validation report) puts the AST-walk primitives in `tests/schema/_walkers.py` (`iter_py`, `iter_top_level_imports(path: Path) -> Iterator[tuple[int, str]]`). S5-04 re-declaring `_Walker` is the third or fourth such re-declaration the kernel exists to prevent — Rule-of-Three was already cleared at S1-07. **Fix:** AC-KERNEL-1 (above) — composition over re-declaration.

#### Harden-tier

27. **(design-patterns — harden) Namespace-chokepoint walker is a four-callers-day-soon kernel candidate.** `test_no_llm_imports_in_sandbox.py` (S1-07), `test_no_subprocess_outside_build_chokepoint.py` (S1-07), `test_stage6_chokepoint.py` (S5-04), and the Phase-7 `test_no_pip_in_distroless_layer.py` (per arch's extension-by-addition pattern) all share the same idiom: walk every `.py`, check imports against a forbidden-prefix set, allowlist exceptions. **Fix:** Notes-for-implementer surfaces the `make_namespace_chokepoint_walker(forbidden_prefix, allowlist) -> Callable[[Path], list[Offender]]` factory as the **next extraction** opportunity (Rule of Three clears at #4); do NOT extract in this story (Rule-2 simplicity wins — three concrete uses, the fourth is hypothetical). Phase-7 story authors get this paragraph in their Context.

28. **(design-patterns — harden) Offender tuple is primitive-obsessed.** Story uses `list[tuple[int, str]]`. A `@dataclass(frozen=True) class Offender: path: Path; lineno: int; symbol: str` is the rule-of-three threshold (three fields, used by main test + planted-positive + failure-message-shape test). **Fix:** AC-OFF-1 — `Offender` is a frozen slots-only dataclass in `tests/schema/_walkers.py` (kernel) OR in this test file if the kernel hasn't shipped the type yet; failure formatting is `Offender.__str__` overridden once (single declaration site per ADR-0010 spirit). Document as Notes if kernel is the right home; do not extract into this story.

29. **(design-patterns — harden) Allowlist constant under-typed.** Story uses `frozenset[Path]`. The membership check after `path.resolve().relative_to(REPO_ROOT)` makes the keys *relative* paths or *strings*. **Fix:** AC-PATH-1 (above) — `_ALLOWLIST: Final[frozenset[str]] = frozenset({"src/codegenie/gates/runner.py", "<S6-04 orchestrator path placeholder>"})`; comparison is `str(path.resolve().relative_to(REPO_ROOT)) in _ALLOWLIST`. Constant lives at module top with an inline comment citing ADR-0001 + the cross-phase TODO for the S6-04 row.

30. **(design-patterns — harden) Surface the policy decision: chokepoint at the **import** boundary, not the call boundary.** The simpler walker (drop `visit_Attribute`) is policy-correct: an aliased call still requires an import, and the import is the structural seam. Document in the walker docstring so a future contributor doesn't "improve" the walker by adding attribute tracking. **Fix:** AC-DOC-1 covers the docstring; the docstring text is pinned to "The chokepoint is the *import*. Aliased call-sites are caught at the alias-binding step (`Import.alias.asname` / `ImportFrom`); attribute access is intentionally not tracked — see Phase-5 ADR-0001 + S5-04 validation report §Design-patterns 30."

#### Nit

31. **(design-patterns — nit) `_walk` accepts `Path` only.** A small ergonomic gap — the planted-positive tests want to walk in-memory strings. **Fix:** AC-WALK-1 — `_walk` (or the kernel function) accepts `Path` for files + a string source variant `_walk_source(source: str, fake_path: Path) -> list[Offender]` for in-memory tests. Two functions, one shared parser. Keeps the kernel surface small.

## Stage 3 — Research

**Skipped.** Every gap was answerable from in-repo precedents:

- `tests/fence/test_no_llm_in_transforms.py` — runtime-closure walker with planted-positive subprocess companion.
- `tests/fence/test_lint_imports_catches_planted_leak.py` — `pytest.fail` over `skip`; CODEOWNERS social anchor; planted-positive parametrization pattern.
- `src/codegenie/transforms/trust_scorer.py` — canonical Stage-6 entrypoint module on `master`.
- `src/codegenie/plugins/subgraph.py` (S6-03 GREEN) — `Stage6ValidateNode` shape per `SubgraphState.trust_outcome`.
- `_validation/S1-07-ci-fence-tests-digests-yaml.md` — `_walkers.py` kernel ownership + planted-positive idiom + relative-path-allowlist precedent.
- `_validation/S5-02-gate-runner-retry-loop.md` — `src/codegenie/gates/runner.py` is the first allowlisted module per AC-PURITY-1 composition-root isolation.
- Phase-3 ADR-0015 — settles `RemediationOrchestrator` shape + unblocks S6-04.

## Edits applied

Every block-tier and harden-tier finding above has been folded into the edited story. The story's `Status` reflects HARDENED. The full set of edits, with before/after snippets, is captured in the story file's new `## Validation notes (2026-05-25)` block (below the Status line).

## Verdict

**HARDENED.** Story is ready for `phase-story-executor` once S1-07 GREENs (`tests/schema/__init__.py` + `_walkers.py` kernel) and S5-02 GREENs (`src/codegenie/gates/runner.py`). The cross-phase orchestrator-wiring concern is deferred to Phase-3 S6-04 with explicit handoff notes; this story ships the structural fence the moment its two same-phase dependencies are in place. The walker passes vacuously on a single-allowlisted-caller codebase, but the parametrized planted-positive guarantees mutation-resistance — a regression in any of the five Python import shapes the walker claims to catch fails loud at PR time.
