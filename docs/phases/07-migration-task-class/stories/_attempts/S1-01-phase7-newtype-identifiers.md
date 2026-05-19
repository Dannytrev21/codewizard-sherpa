# S1-01 Phase 7 — Newtype identifiers + smart constructors — Attempt log

Append-only journal. Every executor pass adds a new entry. **Read the latest
entry first** — it tells you what already shipped and what's deferred.

## Attempt 1 — 2026-05-19 — GREEN

**Executor:** `phase-story-executor` (scheduled task `codewizard-executer`).
**Outcome:** GREEN. All 12 ACs satisfied; full Phase 7 test suite green (98
passed in 2.50s); full repository regression suite green modulo 7
pre-existing env-related failures (lint-imports PATH, secret-in-source SCIP
fixture, docker-sandbox integration tests, golden-test cross-pollution) —
all verified pre-existing on master (`git stash` → run failing tests →
identical 7-test failure set).

### What shipped

- `src/codegenie/types/identifiers.py`:
  - 5 new `NewType` declarations: `ImageRef`, `ImageDigest`, `LayerDigest`, `RuntimeId`, `DockerStageName`.
  - `ProvenanceAdapterId: TypeAlias = tuple["_PhVnLayer", "_PhVnEcosystem"]` declared with `TYPE_CHECKING`-guarded forward-reference import from `codegenie.primitives.vuln_provenance.registry`. Underscored aliases keep the Phase 7 `Ecosystem` distinct from the Phase 3 `Ecosystem` Literal at the symbol level (Validator AC-11 sentinel).
  - 5 new `_NEWTYPE_REGISTRY` rows citing ADR-0004 / ADR-0006 + the immediate Phase 7 consumer.
  - `__all__` extended (sorted) with the 6 new Phase 7 names.
- `src/codegenie/types/parsers.py`:
  - 4 new module-level `Final` constants: `_SHA256_DIGEST_RX`, `_SHA256_DIGEST_LEN`, `_RUNTIME_KEBAB_RX`, `_IMAGE_REF_MAX_LEN`, `_IMAGE_REF_BANNED_CHARS`.
  - 4 new per-newtype `_regex_parser` closures (`_image_digest_match`, `_layer_digest_match`, `_runtime_id_match`, `_docker_stage_name_match`) — separate closures per newtype so `Err.message` distinguishes the two `sha256:` digest types and the two kebab-case types.
  - 5 new public parsers: `parse_image_digest`, `parse_layer_digest`, `parse_runtime_id`, `parse_docker_stage_name`, `parse_image_ref`. The first four route through `_regex_parser`; the fifth carries explicit length / whitespace / control-char / `:`-count checks (deliberate departure — see "Refactor decisions" below).
  - `__all__` extended (sorted) with the 5 new `parse_*` names.
- `src/codegenie/types/__init__.py`:
  - Re-exports the 6 new Phase 7 names; `__all__` extended (sorted union).
- `pyproject.toml`:
  - New `[[tool.mypy.overrides]]` entry for `codegenie.primitives.vuln_provenance.registry` with `ignore_missing_imports = true`. Required because the Phase 7 primitive module lands in S2-01; until then the `TYPE_CHECKING`-guarded forward refs would otherwise fail `mypy --strict` with `import-not-found`. Comment in the override notes the override should be removed once S2-01 lands.
- `tests/unit/types/test_identifiers_phase7.py` — NEW (50 tests covering ACs 1, 2, 3, 4, 5, 8, 9, 10, 11).
- `tests/unit/types/test_identifiers_phase7_mypy_negative.py` — NEW (6 swap-pair tests + 1 negative-control covering AC-6).
- `tests/unit/types/test_parsers_phase7_properties.py` — NEW (14 Hypothesis tests covering AC-7).
- `tests/unit/types/test_identifiers_phase3.py` — extended (additive) with `PHASE7_NEWTYPE_NAMES` + `PHASE7_TYPE_ALIAS_NAMES` constants; `test_all_is_exact_set` updated to include the Phase 7 names; `test_newtype_registry_matches_all` updated to (a) exclude the `TypeAlias` row from the keys-equal-`__all__` invariant and (b) accept ADR-0004 / ADR-0006 citations for Phase 7 entries. No assertion weakened.

### Refactor decisions (design-pattern lens — see story §"Design-pattern observations")

- **Per-newtype closures over shared regexes.** Implemented exactly per the validator's design-patterns critic: `_image_digest_match` and `_layer_digest_match` share `_SHA256_DIGEST_RX` but instantiate separate closures so `Err.message` names the correct newtype. Same shape for `_runtime_id_match` / `_docker_stage_name_match` over `_RUNTIME_KEBAB_RX`. Mirrors Phase 3's `_match`-closure-per-newtype catalog (`parsers.py:131-144`). Verified by `test_layer_digest_error_message_names_layer_digest` + `test_image_digest_error_message_names_image_digest`.
- **`parse_image_ref` deliberately bypasses `_regex_parser`.** The floor checks (length, whitespace, control chars, `:`-count) are not a single regex by design. Documented in the parser's docstring and the story's "Notes for the implementer". Reach-for: a future hardening story can either tighten this to a full Distribution-spec grammar OR keep the explicit-checks shape if BuildKit's grammar drifts.
- **`ProvenanceAdapterId` declared as `TypeAlias`, not `NewType`.** mypy `--strict` rejects `NewType` over a generic tuple (mypy docs §NewType limitations); the alias is the only valid runtime shape. Documented in `Notes for the implementer`.
- **mypy override scope kept minimal.** The override sits next to the Phase 1 `networkx` and `pyarn` overrides — same pattern (named module, `ignore_missing_imports = true`, comment naming the temporal-coupling story that retires the override). No global config change.

### What was tricky

1. **`typing.get_args` on `tuple["X", "Y"]` returns strings, not `ForwardRef`s on Python 3.13.** The original red test asserted `isinstance(args[0], ForwardRef)`. Python 3.13 yields bare strings; older Python yielded `ForwardRef`. Fixed by extracting the forward-ref *name* in either form: `names = tuple(a.__forward_arg__ if isinstance(a, ForwardRef) else a for a in args)`. The intent of the assertion — that the forward references name `_PhVnLayer` / `_PhVnEcosystem` — is preserved.
2. **`mypy --strict` import-not-found on the TYPE_CHECKING ref.** The `TYPE_CHECKING`-guarded import for the Phase 7 `Layer` / `Ecosystem` enums points at a module that lands in S2-01. Without an override, `mypy --strict` reports `import-not-found`. Resolved via the `pyproject.toml` override (see above). Alternative considered: in-line `# type: ignore[import-not-found]` — rejected because the override is the documented Phase 1 / S1-10 / S3-04 pattern and centralises the temporal-coupling info.
3. **Phase 3 regression-test extension required ADR-aware citation logic.** `test_newtype_registry_matches_all` originally asserted every doc contains "ADR-0010". Phase 7 entries cite ADR-0004 / ADR-0006 instead. Extended the test to branch on `name in PHASE7_NEWTYPE_NAMES` — Phase 7 entries must cite ADR-0004 / ADR-0006; everything else must still cite ADR-0010. No assertion weakened; the structural pattern (every entry cites at least one ADR) is preserved.

### Tests added (summary)

| File | Count | Phase 7 ACs covered |
|---|---|---|
| `tests/unit/types/test_identifiers_phase7.py` | 77 cases (incl. parametrize) | AC-1, AC-2, AC-3, AC-4, AC-5, AC-8, AC-9, AC-10, AC-11 |
| `tests/unit/types/test_identifiers_phase7_mypy_negative.py` | 7 cases | AC-6 |
| `tests/unit/types/test_parsers_phase7_properties.py` | 14 cases | AC-7 |
| **Total** | **98** | All 12 ACs |

### Verification gates

```
$ .venv/bin/pytest tests/unit/types/test_identifiers_phase7.py tests/unit/types/test_identifiers_phase7_mypy_negative.py tests/unit/types/test_parsers_phase7_properties.py --no-cov
98 passed in 2.50s

$ .venv/bin/python -m mypy --strict src/codegenie/types/
Success: no issues found in 4 source files

$ .venv/bin/python -m mypy --strict src/
Success: no issues found in 185 source files

$ .venv/bin/python -m ruff check src/codegenie/types/ tests/unit/types/test_identifiers_phase7*.py tests/unit/types/test_parsers_phase7*.py
All checks passed!

$ .venv/bin/lint-imports --config pyproject.toml --no-cache
Contracts: 4 kept, 0 broken.

$ .venv/bin/pytest tests/unit/types/ --no-cov
326 passed in 6.72s
```

Full suite: 5311 passed, 7 pre-existing env failures (verified on master via
`git stash` → re-run → identical 7-test failure set: lint-imports PATH,
secret-in-source SCIP fixture, docker sandbox integration, golden-test
cross-pollution).

### Lessons for the next Phase 7 story

- **The S2-01 implementer must use the Phase 7 `Ecosystem` enum's *string values* — not declaration order — as the within-layer dispatch sort key (ADR-0006).** The string values `"apk"`, `"dpkg"`, `"npm"`, ... become the alphabetic sort key. Document this in the `Ecosystem` enum docstring.
- **The S2-01 implementer should remove the `pyproject.toml` mypy override** for `codegenie.primitives.vuln_provenance.registry` (lines 226-235) once `registry.py` lands with a `py.typed` marker on the package.
- **`test_phase3_ecosystem_is_literal_not_enum` and `test_provenance_adapter_id_is_tuple_alias_with_forward_refs` both carry `# TODO(S2-01)` markers.** Tighten both tests when S2-01 lands the real enums — the assertions become identity-equality against the real `Layer` / `Ecosystem` symbols.
- **Python 3.13 surfaces `tuple["X", "Y"]` args as `str`, not `ForwardRef`.** Forward-ref-introspection tests in future Phase 7 stories should accept both shapes.
