# Story S7-03 — `GitleaksProbe` + mandatory `--redact` + `x-secret-finding` schema tag

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** M
**Depends on:** S7-01, S1-06, S1-09
**ADRs honored:** ADR-0006 (sanitizer Pass 4), `final-design.md` D13 (mandatory `--redact`)

## Context

`GitleaksProbe` (G6) is the secret-scanner. Its defining invariant is **three-layer defense** against raw secret bytes ever leaking into the cache, audit, or `repo-context.yaml`: (1) wrapper-level — `tools.gitleaks.run` raises `ToolInvariantViolation` if `--redact` is absent; (2) `OutputSanitizer` Pass 4 — belt-and-suspenders BLAKE3 fingerprinting; (3) sub-schema — `x-secret-finding: true` JSON Schema tag *requires* `content_hash + entropy_band + length` and *forbids* `match | raw | value | secret | context`. Any one defense catching is sufficient; all three failing is implausible. The adversarial test plants `AKIAFAKE0000000000` and asserts those bytes appear nowhere under `.codegenie/`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #14` — interface, two invocation modes, `--redact` enforcement chain, Pass 4 belt-and-suspenders, finding shape, history-scan opt-in.
  - `../phase-arch-design.md §"Data model" → GitleaksFinding` — required `{content_hash, entropy_band, length}`, forbidden `{match, raw, value, secret, context}`.
  - `../phase-arch-design.md §"Scenarios" → Scenario D` — prompt-injection + secret-bytes redaction walkthrough.
  - `../phase-arch-design.md §"Edge cases"` — `--redact` missing in wrapper → `ToolInvariantViolation`; gitleaks non-zero → `confidence: low`.
- **Phase ADRs:**
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — Pass 4 BLAKE3 fingerprinter contract.
- **Source design:**
  - `../final-design.md §"Conflict-resolution table" D13` — winner `[S]` "mandatory at wrapper level + Pass 4 + x-secret-finding schema tag".
  - `../final-design.md §"Components" §9 OutputSanitizer`.
- **Existing code:**
  - `src/codegenie/tools/gitleaks.py` (S1-06) — wrapper with `--redact` invariant.
  - `src/codegenie/output_sanitizer.py` (S1-09) — Pass 4 secret-finding fingerprinter.
  - `src/codegenie/coordinator/per_file_cache.py` (S7-01) — sub-cache (per-file gitleaks caching).

## Goal

Ship `src/codegenie/probes/gitleaks.py` and `src/codegenie/schema/probes/gitleaks.schema.json` — invokes `tools.gitleaks.run` with `--redact` mandatory; emits `GitleaksFinding[]` with `content_hash + entropy_band + length` and **never** `match | raw | value | secret | context`; sub-schema carries `x-secret-finding: true`; PR-trigger mode opt-in via `--baseline-path`; history scan opt-in (default off).

## Acceptance criteria

- [ ] `src/codegenie/probes/gitleaks.py` exports `GitleaksProbe(Probe)` with `name="gitleaks"`, `declared_inputs=["**/*"]` (filtered by Phase 1 exclusion set), `requires=[]`, `applies_to_languages=["*"]`, `applies_to_tasks=["*"]`, `timeout_seconds=60`.
- [ ] Default invocation: `tools.gitleaks.run(path=<repo>, redact=True, baseline_path=None, no_git=True, format="json", timeout=60)`. PR-trigger mode (config: `gitleaks.baseline_path: <path>`) opt-in for Phase 14; history-scan opt-in (config: `gitleaks.scan_history: bool = False`).
- [ ] Wrapper invariant: `tools.gitleaks.run(redact=False, ...)` → `ToolInvariantViolation` (test asserts the wrapper raises; the probe never invokes with `redact=False`). This is enforced in S1-06; this story exercises it.
- [ ] Per-file findings cache: per `phase-arch-design.md §"Component design" #17` and consistent with semgrep — key = `(content_hash, gitleaks_rules_version, gitleaks_digest)`; on hit, append cached findings; on miss, include file in invocation; write back post-invocation.
- [ ] `GitleaksFinding` Pydantic model with `extra="forbid"` and **exactly** the fields `{rule_id, file, line_start, line_end, commit: str | None, entropy_band ∈ {"low","med","high"}, content_hash: str, length: int}`. **Forbidden field names:** `match`, `raw`, `value`, `secret`, `context` (model raises at construction if any of these appear; tested).
- [ ] `src/codegenie/schema/probes/gitleaks.schema.json` carries the **`x-secret-finding: true`** JSON Schema annotation at the `GitleaksFinding` block level. The schema validator (`_ProbeOutputValidator` from Phase 0) honors this tag: an object so tagged must have `content_hash + entropy_band + length` (required) and must *not* contain `match | raw | value | secret | context` (forbidden). Validator extension for the tag is a one-pass addition.
- [ ] `tests/unit/probes/test_gitleaks.py` covers: happy path on recorded fixture; `--redact` enforced (verify wrapper called with `redact=True`); per-file cache hit on second run; PR-trigger mode invokes with `--baseline-path`; history-scan opt-in (default off → no `--git` invocation); gitleaks non-zero exit → `confidence: low`.
- [ ] **`tests/adv/test_gitleaks_redaction_invariant.py`** plants `AKIAFAKE0000000000` in `tests/fixtures/secret_planted_repo/`; runs `codegenie gather`; asserts those exact bytes appear **nowhere** under `.codegenie/` (recursive grep). Three-layer defense witness.
- [ ] `tests/unit/schema/test_x_secret_finding_tag.py` — synthetic finding with `match: "..."` field → `SchemaValidationError`. Tag enforced at validator level.
- [ ] `tests/golden/gitleaks/<fixture>/expected.json` — golden, `match` / `value` / `raw` not present; `content_hash + entropy_band + length` present.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/probes/gitleaks.py`:
   - `GitleaksProbe(Probe)` with the class attributes above.
   - `async run(self, snapshot, ctx) -> ProbeOutput`:
     1. Read `ctx.config.get("gitleaks", {})` for `baseline_path` and `scan_history`.
     2. Compute `gitleaks_rules_version` (deterministic) from `tools/digests.yaml`.
     3. Per-file cache loop (same shape as semgrep S7-02).
     4. Invoke `tools.gitleaks.run(...)`.
     5. Parse `GitleaksFinding` per output; entropy classification via small helper (`classify_entropy(s: str) -> Literal["low","med","high"]` — Shannon-entropy bucket).
     6. Normalize: each finding's `content_hash` comes from gitleaks output's redacted-secret BLAKE3 (already redacted bytes are themselves hashed — see `phase-arch-design.md` Pass 4 docs for the contract). `length` is the original-secret length (gitleaks redacted output carries length metadata).
     7. Build `ProbeOutput`.
2. Create `src/codegenie/schema/probes/gitleaks.schema.json` with `x-secret-finding: true` on the `GitleaksFinding` block.
3. **Validator extension** (`src/codegenie/schema/validator.py` — Phase 0 origin): if the validator doesn't already support `x-secret-finding`, add a one-pass walker that asserts the tag's contract. *If S1-09's Pass 4 implementation already includes the schema walker, this is a no-op — verify against the S1-09 PR.*
4. Register probe in `probes/__init__.py`.
5. Plant `tests/fixtures/secret_planted_repo/` with one `.env` containing `AWS_ACCESS_KEY_ID=AKIAFAKE0000000000`.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_gitleaks.py`.

```python
import pytest
from codegenie.probes.gitleaks import GitleaksProbe
from codegenie.errors import ToolInvariantViolation

async def test_happy_path_redacts(tmp_repo, ctx, gitleaks_recorded_fixture):
    out = await GitleaksProbe().run(tmp_repo.snapshot, ctx)
    for f in out.slice["findings"]:
        assert all(k not in f for k in ("match", "raw", "value", "secret", "context"))
        assert f["content_hash"] and f["entropy_band"] and f["length"]

async def test_redact_required_at_wrapper(monkeypatch, tmp_repo, ctx):
    async def assert_redact(**kwargs):
        if not kwargs.get("redact"):
            raise ToolInvariantViolation("--redact required")
        return GitleaksResultStub([])  # type: ignore
    monkeypatch.setattr("codegenie.tools.gitleaks.run", assert_redact)
    out = await GitleaksProbe().run(tmp_repo.snapshot, ctx)
    assert out.confidence == "high"

async def test_history_scan_opt_in(tmp_repo, ctx, mocker):
    spy = mocker.spy("codegenie.tools.gitleaks", "run")
    await GitleaksProbe().run(tmp_repo.snapshot, ctx)
    assert spy.call_args.kwargs["no_git"] is True  # default off
```

Adversarial path: `tests/adv/test_gitleaks_redaction_invariant.py`.

```python
from pathlib import Path
from codegenie.cli.main import gather_main

def test_planted_secret_appears_nowhere_in_codegenie(planted_repo):
    gather_main(planted_repo)  # runs the full gather
    secret = b"AKIAFAKE0000000000"
    for p in (planted_repo / ".codegenie").rglob("*"):
        if p.is_file():
            assert secret not in p.read_bytes(), f"secret leaked into {p}"
```

Schema-tag test: `tests/unit/schema/test_x_secret_finding_tag.py`.

```python
import pytest
from codegenie.schema.validator import validate_probe_output
from codegenie.errors import SchemaValidationError

def test_x_secret_finding_forbids_match_field():
    out = {"findings": [{"rule_id": "aws-key", "file": "x", "line_start": 1, "line_end": 1,
                         "commit": None, "match": "secret-bytes", "entropy_band": "high",
                         "content_hash": "abc", "length": 20}]}
    with pytest.raises(SchemaValidationError):
        validate_probe_output("gitleaks", out)
```

### Green

Minimal impl per outline. The validator extension is the only piece touching Phase 0 code — keep it surgical (one schema-walker that scans for `x-secret-finding: true` and checks required/forbidden sets).

### Refactor

- Pull `classify_entropy(value: str) -> Literal["low","med","high"]` into a private helper (S7-03 owns it; not exported). Buckets: `< 3.5 → "low"`, `[3.5, 4.5) → "med"`, `≥ 4.5 → "high"` (Shannon entropy over bytes).
- Module docstring naming `phase-arch-design.md §"Component design" #14`, `final-design.md` D13, ADR-0006.
- Verify `GitleaksFinding` Pydantic forbids the disallowed names via a model validator that raises `ValueError` if any forbidden key appears in `model_extra` — belt-and-suspenders with `extra="forbid"`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/gitleaks.py` | New — `GitleaksProbe` class. |
| `src/codegenie/schema/probes/gitleaks.schema.json` | New — `x-secret-finding: true` tag. |
| `src/codegenie/schema/validator.py` | Surgical — `x-secret-finding` tag walker (if not already in S1-09). |
| `src/codegenie/probes/__init__.py` | Register `GitleaksProbe`. |
| `tests/unit/probes/test_gitleaks.py` | New — 5 unit tests. |
| `tests/adv/test_gitleaks_redaction_invariant.py` | New — planted-secret-never-leaks witness. |
| `tests/unit/schema/test_x_secret_finding_tag.py` | New — validator-tag test. |
| `tests/fixtures/secret_planted_repo/` | New — minimal repo with a planted secret. |
| `tests/golden/gitleaks/happy/expected.json` | New — golden file. |

## Out of scope

- **History scan default on** — refused; opt-in only. Phase 14 may flip the default after PR-trigger mode matures.
- **Custom rule authoring** — gitleaks rules are gitleaks-default + pinned digest; custom rules deferred.
- **PR-trigger webhook** — Phase 14 lands the webhook; this story only ships the `--baseline-path` opt-in.
- **Cross-secret correlation** — clustering similar findings (e.g., same key in multiple files) deferred to Phase 8.
- **`raw` field in cache** — sub-cache stores only the redacted finding shape; never the raw match (cache itself can't carry secrets).

## Notes for the implementer

- **The three-layer defense is the point of this story.** When a reviewer asks "why three layers?", the answer is: wrapper (catches programming errors), Pass 4 (catches sub-schema drift), `x-secret-finding` (catches schema drift). Any one alone is a foot-gun; together they make leakage implausible. Document this in the module docstring.
- **`classify_entropy` is deterministic over the redacted output.** Gitleaks's `--redact` leaves a length-preserving placeholder; you can compute entropy on the *original* bytes only via gitleaks's metadata fields. Use what gitleaks reports (`Entropy: 4.7` in its JSON); fall back to bucket-by-rule-id only if absent.
- **Per-file cache key must include `gitleaks_rules_version`.** If you skip it, an upstream rules bump silently reuses stale findings — the worst class of failure. The version comes from `tools/digests.yaml`'s gitleaks block.
- **The adversarial test's `rglob("*")` recursive grep is the contract.** If a reviewer changes the test to scope-limit, the contract weakens. Keep the recursive scan over **everything** under `.codegenie/` (including audit JSONL, raw artifacts, cache blobs). The bytes must not appear *anywhere*.
- **`x-secret-finding: true` is JSON Schema's vendor-extension space (`x-`-prefixed names are conventionally tolerated).** Standard validators ignore it; ours must honor it. Keep the walker small (one recursive pass) and don't introduce a new dependency.
- **The Pydantic model's `extra="forbid"` will already reject forbidden keys at construction.** The schema-level `x-secret-finding` tag is the second defense (the schema validator runs on the *serialized* output, after Pass 4 — catches Pass 4 misconfig). Both defenses must be in place — don't skip the schema tag thinking the model alone suffices.
- **`commit: str | None`** — gitleaks reports a commit SHA when `--git` (history) is enabled; in default `--no-git` mode, `commit` is `None`. Don't synthesize a value.
