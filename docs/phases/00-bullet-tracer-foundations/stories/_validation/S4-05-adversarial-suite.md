# Validation report — S4-05 Adversarial test suite

**Validated:** 2026-05-13 by `phase-story-validator`
**Verdict:** **HARDENED**
**Story:** [`S4-05-adversarial-suite.md`](../S4-05-adversarial-suite.md)

The story was implementable as written, but four of its eight ACs would have produced tests that *pass* against a clean Phase 0 while *failing to fail* against the regressions they claim to defend — exactly the failure mode an adversarial suite exists to prevent. Three findings were block-severity in the test-quality critic's read; two more were harden-severity multi-AC issues; one was a high-confidence consistency contradiction with the actual codebase state. All were patched in place.

## Stage 1 — Context Brief

### Story snapshot

- **Goal (verbatim):** `pytest tests/adv/ -q` exits 0; the four new test files (`test_path_traversal.py`, `test_symlink_escape.py`, `test_secret_leak.py`, `test_env_var_strip.py`) each pin one structural invariant; a single deliberate regression to the corresponding chokepoint causes the respective test to fail.
- **Non-goals (Out-of-scope):** `test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py` (claimed to be Step 2 — see CON-1 below); `test_pyproject_fence.py` (Step 1); CVE / prompt-injection / fuzz adversarials (later phases); bench tests (S5-01); contributor docs (S5-02).

### Phase / arch constraints invoked

- **ADR-0008** — two-pass sanitizer chokepoint; "field-name regex runs twice — once in `_ProbeOutputValidator`, once in `OutputSanitizer` — closing the bypass-the-validator hole."
- **ADR-0010** — `_ProbeOutputValidator` rejects secret-shaped field names via `SECRET_FIELD_PATTERN`; Pydantic v2 wraps the typed error in `ValidationError`, retrievable via `errors()[0]["ctx"]["error"]` or `__cause__`.
- **ADR-0012** — subprocess allowlist; env "filtered to `{PATH, HOME, LANG, LC_ALL}` ∪ `env_extra`; strips `SSH_AUTH_SOCK`, `AWS_*`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`."
- **Phase-arch-design.md** §Edge cases row 4 (symlink escape) + row 5 (secret-shaped field) + §Testing strategy — Adversarial tests.
- **`coordinator.py:365`** — `if not sanitized.errors: cache.put(...)` — cache-side-effect invariant (failed probes NOT cached).
- **`coordinator.py:317-344`** — `probe.failure` structlog event with `reason=` matching `^SecretLikelyFieldNameError: .+ at \(.+\)$` (S3-05 AC-13 regex).

### Prior validation history

None — first validation pass.

### Open ambiguities found at the end of Stage 1

- **CON-1 candidate (high-priority):** The story's Context block claims `test_no_shell_true.py`, `test_no_network_imports.py`, `test_yaml_unsafe_load.py` were landed in Step 2; the repo's `tests/` tree has no `adv/` subdirectory and `src/codegenie/exec.py:32-35` attributes `test_no_shell_true.py` to S4-05. Treated as a Stage-2 finding rather than a blocker (the four-test scope itself is well-defined).
- **TQ-1 candidate (high-priority):** The story's References claim `Path.resolve(strict=True)` is the path-traversal chokepoint; `cli.py:360` calls `path.resolve()` without `strict=True`. The actual chokepoint is `click.Path(exists=True)` at `cli.py:544`. Treated as a Stage-2 finding.

Both surfaced to Stage 2; no Stage-1 hard stop.

## Stage 2 — Critic reports

### Coverage critic — 8 findings (0 block / 5 harden / 3 nit)

| ID | Severity | Finding | Status |
|---|---|---|---|
| COV-1 | harden | AC-2 fires on wrong invariant — click's `exists=True` rejects before any escape check; test does not distinguish "doesn't exist" from "escapes root" | **Applied** — AC-2 split into 2a (non-existent), 2b (existing-out-of-root, xfail-strict), 2c (no side-effects). References updated. |
| COV-2 | harden | AC-5 misses the `env_extra` sanitization path — the only mutation-relevant surface | **Applied** — AC-5 split into 5a (closed-world parent env) and 5b (`env_extra` with `sensitive_key_dropped` event) plus AC-5b case-insensitivity. |
| COV-3 | harden | AC-4 missing `probe.failure` event + cache-side-effect invariant assertions | **Applied** — AC-4c now requires regex on errors[0], `probe.failure` event with `reason=` regex, recursive `.codegenie/cache/` scan for absence of `"github_token"`. |
| COV-4 | harden | AC-3 doesn't pin event's `path` field VALUE — just count | **Applied** — AC-3 now asserts `escaped[0]["path"] == "link.js"` and the no-resolved-target-leak invariant. |
| COV-5 | harden | AC-3 YAML substring check couples to serializer output format | **Applied** — replaced with `yaml.safe_load` + closed-world dict equality (`counts == {"javascript": 1}`). |
| COV-6 | nit | Goal's mutation-resistance clause has no AC | **Resolved via the per-AC tightening** — Findings 1-5 collectively bind each AC to mechanism-observable evidence, which is the proportionate fix. |
| COV-7 | nit | No AC pins test-isolation (no `default_registry` pollution) | **Applied** — AC-4c explicitly says synthetic probe is NOT decorated with `@register_probe` and the test must NOT mutate `default_registry`. |
| COV-8 | nit | AC-3 doesn't pin "no other adversarial events" | Not applied — out of "one invariant per test" shape. Recorded for posterity. |

### Test-Quality critic — 7 findings (3 block / 2 harden / 2 nit)

| ID | Severity | Finding | Status |
|---|---|---|---|
| TQ-1 | block | Path-traversal test pins the wrong chokepoint (click `exists=True`, not `Path.resolve(strict=True)`); mutation removing repo-root containment wouldn't fail | **Applied** (see COV-1 above) — story References corrected; AC-2a / AC-2b / AC-2c split; explicit "current behavior" note about `path.resolve()` without `strict=True`. |
| TQ-2 | block | Secret-leak coordinator-boundary test is a literal `... # full body in green phase` stub | **Applied** — full concrete skeleton in Implementation outline (with `coordinator.gather(snapshot, task, probes, config, cache, sanitizer)` six-arg dispatch, error-string regex, `probe.failure` assertion, cache-absence walk). |
| TQ-3 | block | Env-strip misses `env_extra` path — the only mutation-relevant surface | **Applied** (see COV-2 above). |
| TQ-4 | harden | Symlink test doesn't assert path-field value or no-leak | **Applied** (see COV-4 above). |
| TQ-5 | harden | Secret-leak doesn't test depth-of-recursion through lists | **Applied** — AC-4b now exercises `{a: {b: [{github_token: ...}]}}` (mirror of `test_probe_output_validator.py::test_secret_key_at_depth_3_via_list_rejected`). |
| TQ-6 | nit | `monkeypatch.setattr("asyncio.create_subprocess_exec", ...)` (global string-form) inconsistent with `monkeypatch.setattr(asyncio, ...)` in existing tests | **Applied** — all four test sketches now use the module-form `setattr(asyncio, "create_subprocess_exec", ...)` matching `tests/unit/test_exec.py`. |
| TQ-7 | nit | Docstring schema not formalized | **Applied** — AC-7 now requires the three-line schema (`Pins:` / `Traces to:` / `Catches:`) and the TDD sketches all use it. |

### Consistency critic — 4 findings (1 block / 1 harden / 2 nit)

| ID | Severity | Finding | Status |
|---|---|---|---|
| CON-1 | block | Story claims Step 2 landed the three AST-scan tests; reality: `tests/adv/` doesn't exist and `exec.py:32-35` attributes them to S4-05 | **Surfaced as Q1 (Open questions)**, not auto-resolved — the validator does not have authority to expand the story's scope from 4 tests to 7 (`phase-story-writer` boundary). Context block corrected to state the reality executably; Step 5 done-criteria flag highlighted. |
| CON-2 | harden | AC-4 doesn't pin ADR-0008's two-pass defense-in-depth (sanitizer pass 2 catches when validator bypassed) | **Applied** — new AC-4d added; TDD sketch monkeypatches `_ProbeOutputValidator.model_validate` to a no-op and asserts the sanitizer catches. Open question Q3 surfaces the coordinator-catches-or-propagates ambiguity. |
| CON-3 | nit | AC-5 wording should reflect "built by omission" not "stripped" | **Applied** — AC-5a now uses closed-world `set(env.keys()) == {...}` equality (the structural form of "built by omission"). |
| CON-4 | nit | AC-4 should explicitly note exit-2 case is out of scope (covered by S4-02) | **Applied** — AC-4c last bullet explicitly defers exit-2 to `tests/unit/test_cli_exit_codes.py` (S4-02). |

## Stage 3 — Researcher

**Skipped** — no findings tagged `NEEDS RESEARCH`. COV-6 (mutation-resistance ACs) was tentatively flagged but the proposed fix-via-per-AC-tightening (which is what landed) is the proportionate and well-precedented approach; full mutation-testing apparatus (mutmut, cosmic-ray) was explicitly noted as out-of-scope for a single story.

## Stage 4 — Synthesizer notes & resolution

### Conflicts between critics

- **None of significance.** Coverage and Test-Quality findings overlapped substantially (COV-1↔TQ-1, COV-2↔TQ-3, COV-3↔TQ-2, COV-4↔TQ-4); the overlap was handled by merging into a single AC-rewrite per concern.
- **Consistency vs. scope** — CON-1 raised a real but story-boundary issue. The validator deliberately did NOT auto-expand S4-05's scope (per skill's anti-goal: "does not rewrite the story's goal or scope"). Instead the contradiction is documented in the Context block and surfaced as Open question Q1 for the user.

### Source-of-truth resolution

- **TQ-1 / COV-1** — the story's References were inaccurate vs. the implementation. Resolution: story References updated to match `cli.py:544`. The "right" invariant (repo-root containment) was retained as AC-2b under `xfail(strict=True)` so the architectural promise stays *executably* visible.
- **CON-2** — ADR-0008 is the source of truth; the defense-in-depth invariant must be asserted somewhere; S4-05's `tests/adv/` is the right home. New AC-4d added.

### Edits applied to the story

The story file was edited in place — see the diff for `S4-05-adversarial-suite.md` in the same commit. Summary of structural changes:

1. New `Validation notes` block under the header (6 numbered findings; status update to "Ready (validated 2026-05-13)"; ADRs-honored split into directly-asserted vs transitive).
2. Context block: removed false "Step 2 already covered three" claim; added explicit "Reality check" paragraph naming the contradiction; preserved scope at four tests.
3. References block: replaced `Path.resolve(strict=True)` claim with `click.Path(exists=True, file_okay=False, path_type=Path)` at `cli.py:544`; expanded code references to include exact line numbers for the chokepoints the tests pin (validator, coordinator, sanitizer, exec).
4. AC list: original 7 ACs reorganized to 8 categorized ACs (path-traversal: 2a/2b/2c; symlink: 3; secret-leak: 4a/4b/4c/4d; env-strip: 5a/5b; plus cross-cutting 6/7/8). Each new AC binds to mechanism-observable evidence (events, regex matches, closed-world env, cache absence).
5. Implementation outline rewritten: per-test sub-test enumeration; concrete `coordinator.gather` six-arg dispatch skeleton with field-list caveat about ADR-0007's byte-frozen `RepoSnapshot`.
6. TDD plan red-test sketches rewritten in full for all four files: path-traversal now has two test functions (nonexistent-refused + existing-outside-root-xfail-strict); symlink-escape now asserts path-value, no-leak, parsed-YAML; secret-leak now has 4 test functions covering top-level + depth-3 + coordinator-boundary + sanitizer-defense-in-depth; env-strip now has 3 test functions (parent-omission + env_extra-filter + case-insensitivity).
7. Notes for the implementer: stripped the false `Path.resolve(strict=True)` reference; added "why two validator-direct tests" rationale; added "why xfail-strict not omission" rationale for AC-2b.
8. New "Open questions surfaced by the validator" block at the end with Q1 (scope), Q2 (S4-02 containment plans), Q3 (coordinator catches vs propagates).

## Verdict rationale

The original story was on the right side of the scope question and named the right chokepoints, but its operational ACs would not have caught the regressions the suite is meant to defend against. The TQ critic's three block-severity findings (path-traversal pinning wrong mechanism, secret-leak coordinator test stubbed, env-strip missing the only mutation-relevant surface) were each a single-PR mutation-attack-surface gap; addressing them moved the story from "four tests that pass" to "four files of tests that *would* fail under a real regression." The CON critic's CON-1 finding is a project-wide scope contradiction that the validator declined to silently resolve — the user must pick Option A (expand) or Option B (sibling story), and Q1 documents the choice. **HARDENED — ready for the executor** with the caveat that Q1 should be answered before this story is implemented (the implementer needs to know whether `tests/adv/__init__.py` is being shared with three other tests).

## Open questions surfaced (mirrored from story body for indexability)

- **Q1 (high):** Expand S4-05 to seven tests (including the three AST-scan tests), or file a sibling story? `exec.py:32-35`'s comment attributes `test_no_shell_true.py` to S4-05; `High-level-impl.md §Step 2 done-criteria` says it was a Step 2 deliverable. Reality says neither story has landed it. Step 5's done-criteria requires all seven to pass before phase exit.
- **Q2 (medium):** Does S4-02 plan to add repo-root containment for the gather argument? If no, AC-2b should be removed rather than kept as a permanent xfail. If yes, AC-2b as currently shaped is correct.
- **Q3 (low):** Should the coordinator catch sanitizer-raised `SecretLikelyFieldNameError` (graceful degrade to `ProbeOutput.errors`) or let it propagate? AC-4d permits either today; whichever the executor picks, an ADR amendment may be warranted.
