# Story S3-01 — `SandboxSpecBuilder.for_gate` + canonical `sandbox_spec_hash`

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready
**Effort:** M
**Depends on:** S1-05 (registries + `env_allowlist`), S1-06 (YAML catalog schema + loader)
**ADRs honored:** ADR-0012 (static env allowlist), ADR-0001 (chokepoint discipline — builder itself touches no subprocess)

## Context

`SandboxSpecBuilder` is the single translator from `(gate, attempt, GateContext)` → frozen `SandboxSpec`. It applies the YAML catalog, the `attempt_overrides` table, the static env allowlist, and computes the BLAKE3-128 `sandbox_spec_hash` over canonical-JSON of the spec. The hash is the cache key Phase 9 will consume and the byte-stability lever the entire integration test suite relies on — if it drifts on Python minor-version or `pyyaml` upgrades, every golden file in Step 3 breaks. The builder is also the only path from host env to `SandboxSpec.env`; without it, ADR-0012 has no enforcement.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — SandboxSpecBuilder` — exact public surface, hash recipe, failure modes (`GateCatalogInvalid`, `SandboxSpecForbidden`).
  - `../phase-arch-design.md §Data model — SandboxSpec` — every field the builder must populate; `sandbox_spec_hash` is the last field.
  - `../phase-arch-design.md §Harness engineering` — "`SandboxSpecBuilder.for_gate(...)` is byte-stable: same inputs → byte-identical `sandbox_spec_hash`".
  - `../phase-arch-design.md §Implementation-level risks #4` — `sandbox_spec_hash` stability across Python minor versions; canonical JSON, never YAML, as hash input.
  - `../phase-arch-design.md §Testing strategy — Property tests` — spec-hash invariant under env reordering.
- **Phase ADRs:**
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — ADR-0012 — `env_allowlist.filter()` is the only host-env → `SandboxSpec.env` path; denied substrings must be filtered even if allowlisted.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — builder lives outside the subprocess chokepoints; no subprocess imports here.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Env into sandbox row` — winner: static allowlist + CI test.
- **Existing code:**
  - `src/codegenie/sandbox/env_allowlist.py` (from S1-05) — `filter(env: Mapping[str,str]) -> Mapping[str,str]`.
  - `src/codegenie/gates/catalog_loader.py` (from S1-06) — schema-validated YAML loader; returns parsed catalog dict.
  - `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxSpec`, `CopyInEntry` frozen models.
- **External docs:**
  - https://github.com/oconnor663/blake3-py — BLAKE3 Python bindings; use `blake3.blake3(data).hexdigest(length=16)` for the 128-bit hex.

## Goal

Translate a YAML gate definition plus a `(gate, attempt, GateContext)` triple into a frozen `SandboxSpec` whose `sandbox_spec_hash` is byte-stable under env-dict reordering and across Python 3.11/3.12.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/spec_builder.py` defines `SandboxSpecBuilder` with `__init__(self, *, catalog_loader: GateCatalogLoader, allowlist: EnvAllowlist)` and `for_gate(self, gate: Gate, attempt: int, ctx: GateContext) -> SandboxSpec`.
- [ ] `attempt_overrides[str(attempt)]` is merged on top of the base spec (deep merge on `phases`, last-wins on scalars); missing override returns the base unchanged.
- [ ] `SandboxSpec.env` is populated only via `allowlist.filter(host_env)`; denied substrings (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`) are absent in the final `env` even when those names appear in the catalog's `env_allowlist` list (defense-in-depth — ADR-0012).
- [ ] `sandbox_spec_hash` is `blake3.blake3(json.dumps(spec_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(length=16)` — JSON path only, never YAML.
- [ ] Property test (hypothesis): for any permutation of `env` dict keys producing the same key-value pairs, `for_gate(...).sandbox_spec_hash` is byte-identical.
- [ ] Golden-file test asserts `tests/golden/sandbox_spec_stage6_validate_attempt1.json` byte-equal to the canonical-JSON of `for_gate(stage6_validate, attempt=1, fixture_ctx)`.
- [ ] `GateCatalogInvalid` is raised when the catalog fails `_schema.json`; `SandboxSpecForbidden` is raised when the post-filter env still contains a denied substring (proves the assertion belt+suspenders).
- [ ] `tests/schema/test_no_subprocess_outside_build_chokepoint.py` remains green (no `subprocess` import added to `spec_builder.py`).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/spec_builder.py`, `pytest` pass.

## Implementation outline

1. Create `src/codegenie/sandbox/spec_builder.py`. Import only `pydantic`, `blake3`, `json`, internal `gates.catalog_loader`, `sandbox.env_allowlist`, `sandbox.contract`. **No `pyyaml` import** — the catalog loader already parsed it; the builder consumes the dict.
2. `for_gate` body: (a) load catalog dict; (b) start from `catalog["sandbox"]`; (c) deep-merge `catalog.get("attempt_overrides", {}).get(str(attempt), {})`; (d) resolve `copy_in` from `ctx.worktree` + per-phase paths; (e) iterate phases to build the flattened `cmd` (Step 3-07's integration test concatenates phases via `&&` or runs them as a single `sh -c`); (f) call `self.allowlist.filter(ctx.host_env)`; (g) construct `SandboxSpec(**partial, sandbox_spec_hash="")`; (h) compute hash on `partial` (the dict *minus* `sandbox_spec_hash`); (i) rebuild with the hash set.
3. Hash function lives in a tiny private helper `_canonical_blake3(d: dict) -> str` so the test suite can call it directly on golden inputs.
4. Raise `SandboxSpecForbidden` if `any(_contains_denied(k) for k in filtered_env)` (defense in depth; should be unreachable if `filter()` is correct).
5. Type hints + structlog event `sandbox.spec.built` with `gate_id`, `attempt`, `sandbox_spec_hash`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths:
- `tests/sandbox/test_spec_builder.py`
- `tests/sandbox/test_spec_hash_property.py`

```python
# tests/sandbox/test_spec_builder.py
import json
from pathlib import Path
import pytest
from codegenie.sandbox.spec_builder import SandboxSpecBuilder
from codegenie.sandbox.env_allowlist import EnvAllowlist
from codegenie.gates.catalog_loader import GateCatalogLoader
from codegenie.sandbox.errors import SandboxSpecForbidden

GOLDEN = Path(__file__).parent.parent / "golden" / "sandbox_spec_stage6_validate_attempt1.json"

def test_for_gate_attempt1_matches_golden(stage6_gate, fixture_ctx, catalog_loader, allowlist):
    """The attempt-1 spec for stage6_validate must byte-equal the committed golden file —
    catches any drift in canonical-JSON serialization, env filtering, or hash recipe."""
    builder = SandboxSpecBuilder(catalog_loader=catalog_loader, allowlist=allowlist)
    spec = builder.for_gate(stage6_gate, attempt=1, ctx=fixture_ctx)
    actual = json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    expected = GOLDEN.read_text()
    assert actual == expected, "spec drifted from golden — review hash/env/canonicalization"

def test_attempt2_override_changes_test_cmd(stage6_gate, fixture_ctx, catalog_loader, allowlist):
    builder = SandboxSpecBuilder(catalog_loader=catalog_loader, allowlist=allowlist)
    spec1 = builder.for_gate(stage6_gate, attempt=1, ctx=fixture_ctx)
    spec2 = builder.for_gate(stage6_gate, attempt=2, ctx=fixture_ctx)
    assert spec1.sandbox_spec_hash != spec2.sandbox_spec_hash
    assert "--maxWorkers=1" in " ".join(spec2.cmd)

def test_denied_substring_in_catalog_allowlist_is_still_filtered(stage6_gate, fixture_ctx_with_secret_key, catalog_loader, allowlist_with_bad_entry):
    """Even if MY_API_KEY is added to env_allowlist by mistake, the substring filter
    catches it — ADR-0012 belt+suspenders."""
    builder = SandboxSpecBuilder(catalog_loader=catalog_loader, allowlist=allowlist_with_bad_entry)
    spec = builder.for_gate(stage6_gate, attempt=1, ctx=fixture_ctx_with_secret_key)
    assert all("KEY" not in k and "TOKEN" not in k for k in spec.env)
```

```python
# tests/sandbox/test_spec_hash_property.py
from hypothesis import given, strategies as st
from codegenie.sandbox.spec_builder import _canonical_blake3

@given(st.dictionaries(st.text(min_size=1, max_size=10), st.text(max_size=20), min_size=0, max_size=8))
def test_hash_invariant_under_env_reordering(env_dict):
    """Reordering env keys must not change the hash — catches non-canonical JSON serialization."""
    base = {"base_image": "x", "cmd": ["true"], "env": env_dict}
    reordered = {"base_image": "x", "cmd": ["true"], "env": dict(reversed(list(env_dict.items())))}
    assert _canonical_blake3(base) == _canonical_blake3(reordered)
```

### Green — make it pass

Minimum builder: read catalog dict, deep-merge attempt overrides, run `allowlist.filter`, construct `SandboxSpec` minus hash, serialize via `json.dumps(..., sort_keys=True, separators=(",", ":"))`, hash with `blake3.blake3(...).hexdigest(length=16)`, reconstruct `SandboxSpec` with hash set. Commit the golden file produced from the deterministic fixture context.

### Refactor — clean up

- Type hints on `_deep_merge`, `_canonical_blake3`.
- Docstrings citing ADR-0012 on `filter` callsite.
- structlog event with stable key set.
- Edge: `attempt_overrides` missing entirely → return base unchanged (don't KeyError).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/spec_builder.py` | New module — the builder + private hash helper. |
| `src/codegenie/sandbox/errors.py` | Add `SandboxSpecForbidden`, `GateCatalogInvalid` (if not already from S1-06). |
| `tests/sandbox/test_spec_builder.py` | New — golden + override + denied-substring assertions. |
| `tests/sandbox/test_spec_hash_property.py` | New — hypothesis env-reorder invariant. |
| `tests/golden/sandbox_spec_stage6_validate_attempt1.json` | New — committed canonical JSON for fixture context. |
| `tests/sandbox/conftest.py` | Fixtures: `stage6_gate`, `fixture_ctx`, `catalog_loader`, `allowlist`, `allowlist_with_bad_entry`. |

## Out of scope

- Calling the builder from `GateRunner` — Step 5 wires it.
- Filling in `sandbox-policy.yaml` content — S3-05 owns that.
- Anything Firecracker-specific — `base_image` field handling is identical across backends; Step 6 reuses this.

## Notes for the implementer

- **Never go through YAML for the hash input.** `pyyaml`'s representer is not version-stable; `json.dumps(..., sort_keys=True, separators=(",", ":"))` is. Risk #4 in `phase-arch-design.md §Implementation-level risks` exists because someone will be tempted to `yaml.safe_dump` here — don't.
- The golden file must be regenerable from a deterministic fixture context (frozen datetime, fixed `workflow_id`, fixed `run_id`). Otherwise the file flakes.
- `Mapping[str, str]` for `SandboxSpec.env` — Pydantic will normalize to `dict[str, str]` for serialization; ensure the post-filter dict's iteration order is stable (Python 3.7+ insertion order, but `sort_keys=True` makes it moot for the hash).
- Don't add `subprocess` here. The fence test will fail PR.
- `blake3-128` = `hexdigest(length=16)` (16 bytes = 32 hex chars). Use that constant; don't hard-code `32`.
- If the static-introspection test (`tests/schema/test_objective_signals_static.py`) flags any string field added here, you've reached too far into signal-land — back out.
