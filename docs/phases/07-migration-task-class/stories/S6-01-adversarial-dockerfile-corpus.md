# Story S6-01 — ≥30-fixture adversarial Dockerfile corpus

**Step:** Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path
**Status:** Ready
**Effort:** M
**Depends on:** S5-08
**ADRs honored:** ADR-P7-006 (`Recipe.engine` `"dockerfile"`), ADR-P7-007 (advisory `dive`), ADR-P7-008 (test-fixture-bundle convention reused for adversarial inputs)

## Context

Phase 7's input surface is *attacker-controllable*: every Dockerfile the orchestrator parses comes from a target repo. The `DockerfileRecipeEngine` (S4-01) and `tools/dockerfile_parse.py` (S2-01) both enforce strict-mode rejection — BOM, UTF-16, CR-only line endings, `ONBUILD`, files > 1 MB, and parse-bombs are refused. None of that is meaningful until a **corpus exists** to exercise it. This story lands the ≥ 30-fixture adversarial Dockerfile corpus that G13 commits to and that S6-02's property tests, S6-09's typosquat/egress adversarials, and Step 7's perf canaries all consume.

This is hardening, not creative scope: every fixture is keyed to a row in `phase-arch-design.md §Edge cases` or a category in `§Fixture portfolio ›tests/adversarial/dockerfiles/`. Fixtures are minimal — the smallest input that demonstrates the hostile category — and labelled with a `README.md` per category so an implementer can map fixture → edge-case row in one hop.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases` rows 1, 3, 10 — the hostile-Dockerfile, typosquat, and BuildKit-heredoc cases the corpus must cover
  - `../phase-arch-design.md §Fixture portfolio ›tests/adversarial/dockerfiles/` — the literal G13 list of ≥ 30 fixture categories (lines 1271)
  - `../phase-arch-design.md §Testing strategy ›Adversarial tests` — corpus is named G13 and feeds property tests, typosquat, and egress block
  - `../phase-arch-design.md §Component 4 ›DockerfileRecipeEngine` — strict-mode rejection list (BOM, ONBUILD, CR-only, > 1 MB, 10 s wall-clock) the fixtures probe
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — strict-mode-only parsing is the rule fixtures exercise
  - `../ADRs/0008-dive-efficiency-advisory-only.md` — ADR-P7-007 — corpus is for parser strictness, NOT for dive growth (which is advisory)
- **Existing code (read these to know what fixtures must defeat):**
  - `src/codegenie/tools/dockerfile_parse.py` — S2-01's strict wrapper; the rejection codes the corpus exercises
  - `src/codegenie/recipes/engines/dockerfile_engine.py` — S4-01's engine; the round-trip property the corpus stress-tests in S6-02
- **External docs (only if directly relevant):**
  - `https://github.com/moby/buildkit/blob/master/frontend/dockerfile/docs/reference.md` — for the canonical Dockerfile grammar the hostile inputs deliberately violate

## Goal

`tests/adversarial/dockerfiles/` contains ≥ 30 minimal Dockerfile fixtures, each tagged in a per-fixture `meta.yaml` with the edge-case category and expected disposition (`parses_cleanly` / `rejected:<reason_code>`), so downstream property tests can iterate the corpus and assert behaviour mechanically.

## Acceptance criteria

- [ ] `tests/adversarial/dockerfiles/` exists and contains **≥ 30** fixture directories, one per category from `phase-arch-design.md §Fixture portfolio` (the full list: BOM, UTF-16-LE, UTF-16-BE, CR-only, mixed CRLF/LF, `ONBUILD`, 2 MB file, parse-bomb, NFC/NFKC, hidden `\r`, Windows-1252, embedded null, 100 MB file (rejected), 200-stage Dockerfile (rejected), `#syntax=` non-first line, `FROM scratch`, multi-platform `FROM`, prompt-injection in `LABEL`, prompt-injection in `RUN`, `ARG x=$(curl atk)`, deeply-nested heredoc, JSON-array `CMD` mixed quote styles, env-var-expanded `FROM`, Dockerfile starting with `# syntax=docker/dockerfile:experimental`, `FROM localhost:5000/<long-redirect-chain>`, trailing null bytes, mid-file UTF-16 BOM, Windows path-separator `FROM`, reflective YAML in `LABEL`).
- [ ] Each fixture directory contains a `Dockerfile` (or `Dockerfile.bin` for binary-only inputs) and a `meta.yaml` with fields: `category` (str — must match a row label from `phase-arch-design.md §Edge cases` or a tag from the `§Fixture portfolio` list), `expected_disposition` (`"parses_cleanly"` | `"rejected"`), `expected_reason_code` (str or `null` — must be one of the `dockerfile.parse_rejected` reason codes; null only when `expected_disposition == "parses_cleanly"`), `edge_case_row` (int or `null` — row number from `phase-arch-design.md §Edge cases`).
- [ ] A `tests/adversarial/dockerfiles/README.md` enumerates every fixture in a markdown table (`fixture | category | edge_case_row | expected_disposition | reason_code`).
- [ ] `tests/adversarial/dockerfiles/_schema.json` exists and `meta.yaml` files validate against it (`jsonschema` library; failure on first invalid fixture).
- [ ] `tests/unit/adversarial/test_corpus_meta_schema.py` exists, lists every fixture under the directory, asserts a `meta.yaml` exists, validates each against `_schema.json`, asserts the corpus has ≥ 30 fixtures, and asserts the **categories are unique** (no two fixtures share the same `category`, except where the category is explicitly a multi-fixture group like `prompt_injection_label` vs `prompt_injection_run`).
- [ ] The corpus contains at least the **rejection** fixtures for: 100 MB file, 200-stage Dockerfile, embedded null, BOM, UTF-16-LE, UTF-16-BE, CR-only, `ONBUILD` — each with the matching `dockerfile.parse_rejected` reason code in `expected_reason_code`.
- [ ] The corpus contains at least one **`parses_cleanly`** fixture for each non-rejection category that S2-01 accepts (e.g., `FROM scratch`, multi-platform `FROM`, `#syntax=` first-line directive).
- [ ] `pytest tests/unit/adversarial/test_corpus_meta_schema.py` passes.
- [ ] `ruff check`, `ruff format --check` clean on touched files. (`mypy --strict` does not run on `tests/` paths; the schema validator test is mypy-strict on `tests/adversarial/conftest.py` if added.)

## Implementation outline

1. Sketch the fixture-directory shape. Decide on `tests/adversarial/dockerfiles/<NN>-<category-slug>/{Dockerfile,meta.yaml}` so directory order is stable and `os.listdir` is deterministic-after-sort.
2. Write `tests/adversarial/dockerfiles/_schema.json` (JSON Schema draft 2020-12) for `meta.yaml`. Five fields, all required.
3. Write the red test `tests/unit/adversarial/test_corpus_meta_schema.py` *first* — it should fail because the corpus does not exist yet (`AssertionError: corpus has 0 fixtures, expected ≥ 30`).
4. Author the fixtures one category at a time. For binary-only inputs (UTF-16, embedded null, BOM, 100 MB), use a small Python helper script `tests/adversarial/dockerfiles/_build_binary_fixtures.py` to generate the `Dockerfile.bin` from a checked-in source `_seeds/*.txt` plus a transform note — *never* commit a 100 MB blob: the 100 MB fixture's `meta.yaml` says `expected_disposition: rejected` and the `Dockerfile.bin` is a sparse / programmatically-generated file the test materializes at runtime.
5. Write the per-category `README.md` table.
6. Run the red test, watch it go green, commit.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/adversarial/test_corpus_meta_schema.py`

```python
# tests/unit/adversarial/test_corpus_meta_schema.py
from pathlib import Path
import json
import yaml
import jsonschema
import pytest

CORPUS = Path(__file__).parent.parent.parent / "adversarial" / "dockerfiles"
SCHEMA = json.loads((CORPUS / "_schema.json").read_text())

def _fixture_dirs() -> list[Path]:
    return sorted([p for p in CORPUS.iterdir() if p.is_dir() and not p.name.startswith("_")])

def test_corpus_has_at_least_thirty_fixtures():
    # arrange: corpus directory must exist
    # act: list fixture directories
    # assert: ≥ 30
    assert len(_fixture_dirs()) >= 30, f"corpus has {len(_fixture_dirs())} fixtures, expected ≥ 30 (G13)"

def test_every_fixture_has_valid_meta_yaml():
    for d in _fixture_dirs():
        meta_path = d / "meta.yaml"
        assert meta_path.exists(), f"{d.name}: meta.yaml missing"
        meta = yaml.safe_load(meta_path.read_text())
        jsonschema.validate(meta, SCHEMA)  # raises ValidationError on first bad fixture

def test_every_rejection_fixture_names_a_reason_code():
    for d in _fixture_dirs():
        meta = yaml.safe_load((d / "meta.yaml").read_text())
        if meta["expected_disposition"] == "rejected":
            assert meta["expected_reason_code"] is not None, f"{d.name}: rejected fixture must name a reason code"

def test_fixture_categories_are_unique_or_explicitly_grouped():
    seen: dict[str, str] = {}
    for d in _fixture_dirs():
        meta = yaml.safe_load((d / "meta.yaml").read_text())
        cat = meta["category"]
        if cat in seen:
            pytest.fail(f"duplicate category '{cat}' between {seen[cat]} and {d.name}")
        seen[cat] = d.name
```

The red is `AssertionError: corpus has 0 fixtures, expected ≥ 30`. Commit the test, watch it fail, then start authoring fixtures.

### Green — make it pass

For each category, create the directory + `Dockerfile` + `meta.yaml`. The smallest content that demonstrates the category. For `BOM` it's three bytes `\xef\xbb\xbf` followed by `FROM scratch\n`; for `ONBUILD` it's `FROM scratch\nONBUILD RUN echo hi\n`; for `parse_bomb` it's `FROM scratch AS a\nFROM a AS a\n` repeated. Add fixtures in alphabetical category-slug order to keep the diff readable.

### Refactor — clean up

- Add `tests/adversarial/dockerfiles/README.md` with the canonical mapping table.
- Add `_build_binary_fixtures.py` for fixtures whose source is too noisy to read as a binary file (e.g., the 100 MB sparse file is generated at test collection time via a `conftest.py` autouse fixture, *not* checked in).
- Add a `conftest.py` under `tests/unit/adversarial/` if needed to materialize the size-cap fixtures lazily.
- Ensure no fixture exceeds 5 KB checked-in size except `meta.yaml` cross-references the runtime-materialization script.
- Honour `phase-arch-design.md §Edge cases` row 1 — every "rejected" fixture's `expected_reason_code` matches the literal string the parser raises.

## Files to touch

| Path | Why |
|---|---|
| `tests/adversarial/dockerfiles/<NN>-<category>/Dockerfile` (× ≥ 30) | New — minimal hostile Dockerfile per category |
| `tests/adversarial/dockerfiles/<NN>-<category>/meta.yaml` (× ≥ 30) | New — fixture metadata; validates against `_schema.json` |
| `tests/adversarial/dockerfiles/_schema.json` | New — JSON Schema for `meta.yaml` |
| `tests/adversarial/dockerfiles/README.md` | New — fixture-table cross-reference |
| `tests/adversarial/dockerfiles/_build_binary_fixtures.py` | New — runtime materialization for size-cap and binary-only fixtures |
| `tests/unit/adversarial/test_corpus_meta_schema.py` | New — red test; anchors corpus shape |
| `tests/unit/adversarial/conftest.py` | New (optional) — autouse fixture that materializes the 100 MB and large-binary fixtures lazily, so the git tree stays small |

## Out of scope

- **Property tests over the corpus.** Handled by S6-02 (round-trip equivalence, image-name allowlist, ledger serialization, gate-predicate label invariance).
- **The typosquat catalog poisoning adversarial.** Handled by S6-09 (`tests/adversarial/typosquat_lookup.py`).
- **The egress-block adversarial.** Handled by S6-09 (`tests/adversarial/build_egress_blocked.py`).
- **Live-running S2-01's wrapper against the corpus.** This story is *fixture authoring* only. S6-02 wires the corpus into property tests; S2-01 is already green from Step 2.
- **`cve_image_recommendations.yaml` poisoning fixture.** Not in G13's corpus list; handled implicitly by the typosquat regex test in S6-09.

## Notes for the implementer

- The 100 MB fixture is a **rejection** fixture. Do not commit a 100 MB blob to git. The `meta.yaml` declares the expected size and a `conftest.py` autouse fixture writes a sparse file before the test runs (`fp.truncate(100 * 1024 * 1024)`). Same posture for any large binary.
- Fixture **categories** are the source of truth — not directory names. The numbering prefix (`01-`, `02-`, ...) is for stable enumeration only; renaming a directory is free as long as `meta.yaml.category` is stable.
- The `parse_bomb` fixture is the one most likely to mis-fire — a recursive `FROM ... AS ...` chain is a parser-pathological *legal* input, not a syntax error. S2-01's 10 s subprocess wall-clock is what kills it. Confirm `expected_reason_code: "subprocess_wall_clock_exceeded"` aligns with what S2-01 raises.
- The `prompt_injection` fixtures must not trigger any LLM call during the corpus tests — the sanitizer is exercised in `tests/unit/probes/test_shell_invocation_trace.py`, not here.
- For `multi_platform_from` (`FROM --platform=$BUILDPLATFORM ...`), the disposition is **`parses_cleanly`** with `confidence=low` *at the probe layer*, not at the parser layer. Mark `expected_disposition: parses_cleanly`.
- `#syntax=docker/dockerfile:experimental` as the **first line** is `parses_cleanly`; as a **non-first** line is `rejected` (S2-01 strict mode). Author two distinct fixtures — `syntax-directive-first-line` (clean) and `syntax-directive-mid-file` (rejected, reason `parse_directive_not_first`).
- Per the manifest's cross-cutting rules: when this story lands, update the story file's `Status:` to `Done` and ensure CI's `ruff check` on `tests/adversarial/` is clean. Mypy strict does not run on `tests/`, so type-check is via the `conftest.py` only if needed.
