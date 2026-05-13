# Story S2-06 — Distroless catalog seed + `render_base_catalog()` / `read_base_catalog()`

**Step:** Step 2 — Tool wrappers and the pre-rendered base catalog hot view
**Status:** Ready
**Effort:** M
**Depends on:** S1-07, S2-05
**ADRs honored:** ADR-0009 (contract-surface snapshot — `base_catalog.json` shape is captured under `#base_catalog`), ADR-P7-002 (the catalog produces the `cgr.dev` references that go through the additive egress allowlist), ADR-0013 (shell-trace gate-time — distroless catalog underwrites the gate-time validation chain)

## Context

This story lands the *hot view* every distroless workflow reads at `resolve_target_image`: `.codegenie/cache/base_catalog.json`, rendered from the hand-curated YAML seed `src/codegenie/catalogs/distroless/cve_image_recommendations.yaml`. The shape is **Phase-8-compatible** — Phase 8's supervisor (next phase) lifts this file into Redis without schema work (ADR-0013, `phase-arch-design.md §Integration with Phase 8`). Schema-versioned (`Literal["v0.7.0"]`), pinned digests, staleness signal (`catalog_row_age_h`) — all the load-bearing fields that Phase 13's calibration can read later.

The seed must include **≥ 3 rows for Node, Go, Python** so the Step 5 E2E (Express → distroless Node), the Step 6 static-Go E2E, and the catalog property tests have real data to bind to. The round-trip property — `render → read → equal-by-schema` — is what guarantees the snapshot canary (S1-07) catches drift on either side of the boundary.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 9. Pre-rendered base_catalog.json hot view` (lines ~748–780) — full spec: `render_base_catalog()`, `read_base_catalog()`, JSON shape with `schema_version`, `snapshot_sha`, `chainguard_index_snapshot`, `rendered_at`, `rows`.
  - `../phase-arch-design.md §Data model ›Contracts` — `BaseCatalogHotView` and `TargetImageRecommendation` Pydantic models, both `extra="forbid", frozen=True`.
  - `../phase-arch-design.md §Edge cases #3` (typosquat — `to_image` allowlist regex `^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}|:[a-z0-9._-]+)$`).
  - `../phase-arch-design.md §Edge cases #12` ("catalog_row_age_h > 2160 → confidence=medium") — staleness signal.
  - `../phase-arch-design.md §Integration with Phase 8` (lines ~1315+) — Phase 8 lifts `.codegenie/cache/base_catalog.json` into Redis with no schema work.
- **Phase ADRs:**
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — `tools/contract-surface.snapshot.json#base_catalog` is the canonicalized shape; round-trip must match.
  - `../ADRs/0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md` — distroless catalog underwrites the gate-time validation.
- **Source design:**
  - `../final-design.md §"Departures"` — staleness signal rationale.
- **High-level impl:**
  - `../High-level-impl.md §Step 2` (lines 60–82) — features delivered; explicit ≥3 rows for Node, Go, Python.
  - `../High-level-impl.md §Open implementation questions #5` — `base_catalog.json` schema versioning for Phase 8's Redis lift; pinned `Literal["v0.7.0"]`.
  - `../High-level-impl.md §Open implementation questions #7` — automated ingest deferred to Phase 14.

## Goal

`render_base_catalog()` reads the hand-curated YAML seed and writes `.codegenie/cache/base_catalog.json` whose Pydantic schema matches `tools/contract-surface.snapshot.json#base_catalog` exactly; `read_base_catalog()` round-trips the same payload back as a Pydantic-typed `BaseCatalogHotView`.

## Acceptance criteria

- [ ] `src/codegenie/catalogs/distroless/cve_image_recommendations.yaml` has ≥ 3 rows for each of Node, Go, Python (so ≥ 9 rows total, all with real-shaped `cgr.dev/chainguard/...` references — the digests can be `sha256:<64 hex>` placeholders for the seed but must pass the image-name allowlist regex).
- [ ] `src/codegenie/catalogs/distroless/_schema.json` is a JSON Schema (or Pydantic-derived schema) describing one row; `tests/unit/catalogs/test_distroless_catalogs.py` validates every YAML row against it (closed-enum CI gate on `confidence_band`).
- [ ] `render_base_catalog(out: Path = Path(".codegenie/cache/base_catalog.json")) -> None` writes a JSON file with the exact `BaseCatalogHotView` shape — `schema_version: "v0.7.0"`, `snapshot_sha` (sha of the source YAML), `chainguard_index_snapshot` (placeholder value pinned in `tools/digests.yaml` until Phase 14 automates), `rendered_at` (ISO 8601 UTC), `rows: dict[from_image_str, TargetImageRecommendation]`.
- [ ] `read_base_catalog(path: Path) -> BaseCatalogHotView` returns the typed Pydantic; `model_validate_json` enforces `extra="forbid"` + `Literal["v0.7.0"]`.
- [ ] **Round-trip property**: render → read → assert equality on all fields (Pydantic deep `==`) — captured as `tests/unit/catalogs/test_distroless_catalogs.py::test_render_read_roundtrip`.
- [ ] `tests/integration/test_base_catalog_snapshot_shape.py` asserts the rendered JSON canonicalizes (sorted keys, fixed separators) to the same bytes that `tools/contract-surface.snapshot.json#base_catalog` describes — this is what makes S1-07's snapshot canary catch drift on either side.
- [ ] Every `to_image` value in the seed passes the regex `^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}|:[a-z0-9._-]+)$` (Edge case #3 typosquat defense).
- [ ] Atomic write: `render_base_catalog()` writes to a temp file under `.codegenie/cache/` and renames into place (so a partial render never corrupts a concurrent `read_base_catalog`); the write is `cache_lock`-coordinated using S2-05's primitive.
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/catalogs/test_distroless_catalogs.py` and `pytest tests/integration/test_base_catalog_snapshot_shape.py` all pass.
- [ ] Fence-CI confirms no `anthropic|chromadb|sentence-transformers` imports.

## Implementation outline

1. Author the YAML seed `cve_image_recommendations.yaml` with ≥ 3 rows for Node, Go, Python. Use realistic Chainguard image references: `cgr.dev/chainguard/node:20-distroless`, `cgr.dev/chainguard/go:1.22-distroless`, `cgr.dev/chainguard/python:3.12-distroless` (etc.). Pin `sha256:<placeholder-64-hex>` per row.
2. Author `_schema.json` (JSON Schema draft 2020-12 or Pydantic-derived) for a single row.
3. Write failing tests in `tests/unit/catalogs/test_distroless_catalogs.py` and `tests/integration/test_base_catalog_snapshot_shape.py`. Commit.
4. Implement `BaseCatalogHotView` and `TargetImageRecommendation` Pydantic models (`extra="forbid", frozen=True`) in `src/codegenie/catalogs/distroless/__init__.py` (or a dedicated `models.py`).
5. Implement `render_base_catalog()`:
   - Read the YAML seed via `yaml.safe_load`.
   - Validate every row against `_schema.json` / Pydantic.
   - Enforce the `to_image` allowlist regex; raise `CatalogPoisoned(reason="typosquat", row=...)` on failure.
   - Compute `snapshot_sha = blake3(<yaml_bytes>).hexdigest()`.
   - Read `chainguard_index_snapshot` from `tools/digests.yaml` (placeholder until Phase 14).
   - Assemble `BaseCatalogHotView`; canonical-JSON serialize (sorted keys, `(",", ":")` separators); atomic-write under `cache_lock` (S2-05).
6. Implement `read_base_catalog()`: read bytes, validate via Pydantic, return typed object.
7. Refactor; mypy strict; fence-CI.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/catalogs/test_distroless_catalogs.py`

```python
# tests/unit/catalogs/test_distroless_catalogs.py
import json
import re
from pathlib import Path
import pytest
from codegenie.catalogs.distroless import (
    render_base_catalog,
    read_base_catalog,
    BaseCatalogHotView,
    TargetImageRecommendation,
    CatalogPoisoned,
)

_CGR_REGEX = re.compile(
    r"^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}|:[a-z0-9._-]+)$"
)


def test_seed_yaml_has_three_rows_each_for_node_go_python():
    """≥3 rows for each of Node, Go, Python — the Step 5/6 E2Es bind to these."""
    rendered = Path(".codegenie/cache/base_catalog.json")
    render_base_catalog(out=rendered)
    view = read_base_catalog(rendered)
    from_images = list(view.rows.keys())
    node = [k for k in from_images if "node" in k.lower()]
    go = [k for k in from_images if "go" in k.lower() or "golang" in k.lower()]
    py = [k for k in from_images if "python" in k.lower()]
    assert len(node) >= 3, f"need ≥3 Node rows, got {len(node)}"
    assert len(go) >= 3, f"need ≥3 Go rows, got {len(go)}"
    assert len(py) >= 3, f"need ≥3 Python rows, got {len(py)}"


def test_every_to_image_passes_chainguard_allowlist(tmp_path):
    """Edge case #3 — typosquat defense via image-name regex on every row."""
    out = tmp_path / "base_catalog.json"
    render_base_catalog(out=out)
    view = read_base_catalog(out)
    for from_image, rec in view.rows.items():
        assert _CGR_REGEX.match(rec.to_image), (
            f"to_image violates allowlist: {rec.to_image} (from {from_image})"
        )


def test_render_read_roundtrip(tmp_path):
    """Render → read → deep-equal on the typed payload."""
    out = tmp_path / "base_catalog.json"
    render_base_catalog(out=out)
    a = read_base_catalog(out)
    # Re-render to a second path; read back; they must be equal.
    out2 = tmp_path / "base_catalog2.json"
    render_base_catalog(out=out2)
    b = read_base_catalog(out2)
    # rendered_at will differ by clock; compare ignoring that:
    a_dict = a.model_dump()
    b_dict = b.model_dump()
    a_dict.pop("rendered_at")
    b_dict.pop("rendered_at")
    assert a_dict == b_dict


def test_schema_version_pinned_v0_7_0(tmp_path):
    """schema_version is closed Literal — Phase 8 Redis lift relies on this pin."""
    out = tmp_path / "base_catalog.json"
    render_base_catalog(out=out)
    payload = json.loads(out.read_text())
    assert payload["schema_version"] == "v0.7.0"


def test_render_rejects_poisoned_seed_loudly(tmp_path, monkeypatch):
    """Typosquat in the seed → CatalogPoisoned, not silent acceptance."""
    # Patch the YAML loader to inject a poisoned to_image.
    def fake_load(_):
        return {
            "rows": [
                {
                    "from_image": "node:20-bullseye",
                    "to_image": "cgr.dev/chamguard/node:20",  # typosquat
                    "pinned_digest": "sha256:" + "a" * 64,
                    "cve_basis": [],
                    "confidence_band": "high",
                    "catalog_row_age_h": 4,
                }
            ]
        }
    monkeypatch.setattr("codegenie.catalogs.distroless._load_seed", fake_load)
    with pytest.raises(CatalogPoisoned):
        render_base_catalog(out=tmp_path / "out.json")
```

Test file path: `tests/integration/test_base_catalog_snapshot_shape.py`

```python
# tests/integration/test_base_catalog_snapshot_shape.py
import json
from pathlib import Path
from codegenie.catalogs.distroless import render_base_catalog, read_base_catalog


def test_rendered_shape_matches_contract_surface_snapshot(tmp_path):
    """The rendered JSON's keys / Pydantic schema match
    tools/contract-surface.snapshot.json#base_catalog (S1-07 frozen). Drift here
    must trigger the canary."""
    out = tmp_path / "base_catalog.json"
    render_base_catalog(out=out)
    payload = json.loads(out.read_text())
    snap = json.loads(Path("tools/contract-surface.snapshot.json").read_text())
    expected_keys = set(snap["base_catalog"]["top_level_keys"])
    assert set(payload.keys()) == expected_keys, (
        f"rendered keys diverge from snapshot. "
        f"missing={expected_keys - set(payload.keys())}, "
        f"extra={set(payload.keys()) - expected_keys}"
    )
```

Run; confirm `ImportError` / `AssertionError`; commit.

### Green — make it pass

- Add `src/codegenie/catalogs/distroless/__init__.py` with the Pydantic models, `render_base_catalog`, `read_base_catalog`, `CatalogPoisoned`.
- Add `src/codegenie/catalogs/distroless/cve_image_recommendations.yaml` with the seed rows.
- Add `src/codegenie/catalogs/distroless/_schema.json` describing one row.
- Implement `_load_seed` as a separable helper so the poisoned-seed test can monkey-patch it.
- Wrap the write in `cache_lock(out.with_suffix(".lock"))` from S2-05.

### Refactor — clean up

- Docstrings; type hints.
- `structlog` event `catalog.rendered` with `row_count`, `snapshot_sha`, `wall_clock_ms`.
- Document in the module docstring that `chainguard_index_snapshot` is a hand-pinned placeholder for Phase 7 (Phase 14 automates the ingest per Open implementation question #7).
- Confirm the canonical JSON serialization is byte-stable across runs (sorted keys, `separators=(",", ":")`, no trailing newline) — this is what makes the snapshot diff truthful.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/catalogs/distroless/__init__.py` | New — Pydantic models, render/read, exception. |
| `src/codegenie/catalogs/distroless/cve_image_recommendations.yaml` | New — hand-curated seed, ≥3 rows for Node/Go/Python. |
| `src/codegenie/catalogs/distroless/_schema.json` | New — JSON Schema for one row. |
| `tests/unit/catalogs/test_distroless_catalogs.py` | New — happy path, allowlist, round-trip, schema_version, poisoned-seed. |
| `tests/integration/test_base_catalog_snapshot_shape.py` | New — confirms the rendered shape lines up with the S1-07 contract snapshot. |
| `tools/digests.yaml` | Add the placeholder `chainguard_index_snapshot` value (Phase 14 will automate). |

## Out of scope

- **Automated catalog ingest from Chainguard's registry** — deferred to Phase 14 (Open implementation question #7).
- **`resolve_target_image` graph node consumption** — S5-02 wires the mmap read.
- **Phase 8 Redis lift** — Phase 8 (next phase) reads this exact JSON; this story only guarantees shape compatibility (ADR-0013).
- **Image-dialect rules / `image_dialect_rules.yaml`** — Phase 7 ships the CVE → image YAML; dialect rules are a downstream Step 4 / Step 5 concern.
- **Pre-warm strategy for `cgr.dev`** — operator follow-up (Open implementation question #6).

## Notes for the implementer

- The seed YAML's `pinned_digest` values can be placeholder `sha256:<64-hex>` strings as long as they pass the allowlist regex; real digests get filled in when an operator follow-up wires `imagetools_inspect` (S2-02) to resolve them. **Surface the placeholder status in the file's leading comment** so a future maintainer doesn't deploy these as if they were real.
- The `confidence_band` field is a closed `Literal["high","medium","low"]`. Property tests in S6-02 will exercise it; do not invent new bands here.
- `catalog_row_age_h > 2160` (≈ 90 days) is the staleness threshold from Edge case #12. The threshold itself is not enforced in this story (it surfaces in `BaseImageProbe`'s confidence computation in S3-01); but the *field* must be present in every row so the probe can read it.
- The atomic write pattern (`tmp + os.replace`) is what guarantees a concurrent `read_base_catalog` never sees a partial file. Combined with `cache_lock`, this also prevents two `render_base_catalog` calls from racing.
- `chainguard_index_snapshot` is intentionally a placeholder in Phase 7 — the value is "hand-pinned by the operator who runs `codegenie catalog render`." Phase 14 will replace this with a real Chainguard upstream-snapshot fingerprint. Document this in the module docstring and the YAML's leading comment so the placeholder isn't mistaken for a bug.
- The Phase 8 lift hinges on the JSON shape, not on the on-disk path. Phase 8 reads `BaseCatalogHotView` Pydantic and pushes the same shape into Redis — keep `extra="forbid"` and avoid `Any`-typed fields anywhere in the model graph.
- Rule 9 / Rule 12: typosquat detection raises `CatalogPoisoned` loudly; do not coerce a poisoned row to a "low confidence" pass. The whole point of the allowlist regex is hard rejection.
