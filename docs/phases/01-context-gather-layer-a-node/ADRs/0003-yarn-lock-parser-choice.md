# ADR-0003: `yarn.lock` parser — `pyarn` if maintained, else hand-rolled fallback

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** parser · dependency-policy · maintenance-burden · land-time-decision
**Related:** ADR-0009, [Phase 0 ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-pyproject-toml-extras-shape.md)

## Context

`NodeManifestProbe` must parse `yarn.lock` to enumerate dependencies and detect native modules. The performance lens proposed a ~1000-LOC hand-rolled parser by default, justifying ~200 ms of warm-cache-miss savings. The critic (`critique.md "Attacks on the performance-first design"` #4) demolished the math: the design's own ≥ 92% steady-state cache-hit-rate target means a 200 ms parser improvement contributes ~16 ms to the *average* gather. A 1000-LOC parser is not justified by 16 ms of average latency.

The best-practices lens proposed `pyarn` (PyPI) if maintained, with a hand-rolled fallback. The security lens emphasized "no regex backtracking" if hand-rolling — a deterministic line-scanner. The synthesis adopted `[B]`'s rule but punts the actual decision to land-time because PyPI dep maintenance status is time-sensitive.

This is the **one** Phase 1 third-party Python dep addition (`pyarn`); ADR-0009 records the broader "no new C-extension parser drift" rule that this decision honors.

## Options considered

- **Ship hand-rolled by default (`[P]`).** Always use the ~1000-LOC line scanner. No external dep. Maximum maintenance burden; critic-dismantled latency justification.
- **Use `pyarn` always.** Maintained PyPI lib. Adds one dep; risk if `pyarn` falls into abandonment (next CVE feed nobody watches).
- **Pin a `pyarn` version; ship a hand-rolled fallback module that's only imported on `ImportError`.** Two implementations in tree forever; parity test risk (Gap #3 in `phase-arch-design.md`).
- **`pyarn` if maintained at land-time, else hand-rolled as default.** Defer the binary choice to the implementer; ship one parser; ADR records the rule and the maintenance heuristic.

## Decision

**At Phase 1 land-time, the implementer evaluates `pyarn`'s maintenance status against the heuristic:**

- **< 18 months since last release** AND **passes the Phase 1 fixture suite** AND **no open CVE** → ship `pyarn` as `_lockfiles/_yarn.py`'s parser, with `pyarn` listed in `pyproject.toml`'s `gather` extras.
- **Otherwise** → ship the ~100-line hand-rolled line-scanner (no regex over the full file; line-by-line state machine for section headers and entries) as `_lockfiles/_yarn.py`'s implementation, with `pyarn` *not* in the dep closure.

The implementer's decision is **recorded as a note appended to this ADR at land-time**, with the date and the heuristic check results. The selection lives at module-load via `_HAS_PYARN: bool` (computed via `importlib.util.find_spec`); the rule is what's ADR'd, not the current choice.

A parity test (`tests/unit/probes/test_yarn_parser_oracle.py`, per `phase-arch-design.md` Gap 3) validates both implementations against (a) hand-curated fixtures with expected output AND (b) lockfile-bytes-derived oracle invariants (every output name appears in lockfile text; every output version appears against its name; counts align). The two-direction validation catches silent divergence in either parser.

## Tradeoffs

| Gain | Cost |
|---|---|
| Avoids a ~1000-LOC maintenance liability if `pyarn` is healthy at land-time | Decision lives in two places — code (`_HAS_PYARN`) and this ADR's land-time note |
| Hand-rolled fallback exists for the abandonment scenario; users on machines without `pyarn` still parse | Two implementations to keep in sync via parity test (the maintenance cost of `pyarn` getting abandoned later) |
| `pyarn` is a YAML-format-adjacent parser, not a C extension; doesn't violate ADR-0009 | One PyPI dep added (conditional); one more entry in `pip-audit` / `osv-scanner` watchlist |
| Two-direction parity test (Gap 3 mitigation) catches silent bugs in either implementation independently | Oracle invariants must be maintained as `yarn.lock` format evolves; tied to fixture portfolio in `tests/fixtures/node_yarn_legacy/` |
| Hand-rolled fallback is deterministic, no regex backtracking — meets the security lens's no-ReDoS bar | Hand-rolled parser shape is not specified beyond "line scanner + state machine"; implementer chooses |
| The decision is land-time, not design-time — minimizes ADR-vs-reality drift if `pyarn`'s status changes between design and ship | Reviewers must read the land-time note appended to this ADR to know the current state |

## Consequences

- `src/codegenie/probes/_lockfiles/_yarn.py` declares `_HAS_PYARN: bool` at module load. `parse(path)` dispatches accordingly. Both code paths return the same `YarnLock` `TypedDict`.
- `pyproject.toml` lists `pyarn` under `gather` extras (Phase 0 ADR-0006 extras shape) only if the land-time evaluation selects it. Otherwise the extras list is unchanged.
- The parity test runs unconditionally (it constructs the hand-rolled parser inline if `_HAS_PYARN` is true; the hand-rolled module ships either way).
- `tests/unit/probes/test_yarn_parser_oracle.py` is the load-bearing regression — its oracle invariants are independent of either parser's implementation.
- A future maintenance-status change (e.g., `pyarn` abandoned three years post-ship) triggers an ADR amendment that flips the selection rule and re-runs the parity tests.
- The land-time note shape: `### Implementer's land-time selection (YYYY-MM-DD): chose <pyarn|hand-rolled>; rationale: …`

## Reversibility

**High.** Switching parsers is mechanically `_HAS_PYARN`-flag change plus pyproject edit; the wire contract (`YarnLock` TypedDict) is parser-agnostic. The parity test guarantees both paths return identical output for in-fixture lockfiles. Repos with cached `node_manifest` blobs continue to validate (the slice shape is parser-independent).

## Evidence / sources

- `../final-design.md "Components" #4 NodeManifestProbe` — three-way lockfile parsers
- `../final-design.md "Conflict-resolution table" row 5` — the resolution
- `../final-design.md "Open questions deferred to implementation" #1` — the land-time decision rule
- `../phase-arch-design.md "Component design" #9 Lockfile parsers` — interface
- `../phase-arch-design.md "Gap analysis & improvements" Gap 3` — the two-direction parity test
- `../phase-arch-design.md "Edge cases" row 10` — `pyarn` uninstall path
- `../critique.md "Attacks on the performance-first design"` #4 — latency-math demolition
- ADR-0009 — the broader dep-closure stance this lives inside

## Implementer's land-time selection

### Implementer's land-time selection (2026-05-14): chose hand-rolled

**Date:** 2026-05-14 (Phase 1, story S3-03)

**Selection:** **hand-rolled** (~80-line line-by-line state machine in `_lockfiles/_yarn.py::_parse_handrolled`).

**Heuristic check results:**

- **`pyarn` last release:** `0.3.0` on **2024-10-30** (verified via PyPI JSON API at https://pypi.org/pypi/pyarn/json). The 18-month-vs-2026-05-14 cutoff is **2024-11-14**; `pyarn 0.3.0` is **15 days outside** that window. **FAILS** the freshness criterion.
- **Open CVE scan:** OSV.dev `POST /v1/query {"package":{"name":"pyarn","ecosystem":"PyPI"}}` returned `{}` (no advisories). **PASSES** the CVE criterion.
- **Fixture-suite confirmation:** Not exercised. The S3-03 hand-rolled scanner parses `tests/fixtures/node_yarn_legacy/yarn.lock` (the lone Phase 1 yarn fixture) directly — confirmed by `tests/unit/probes/_lockfiles/test_yarn.py::test_parse_happy_path_handrolled_yields_entries` and the local fuzz harness `tools/fuzz_yarn_lock.py`. Two-direction parity is **S3-04's** contract; deferred.
- **License compatibility:** `pyarn 0.3.0` is **GPLv3+** (see wheel `pyarn-0.3.0.dist-info/METADATA` `Classifier: License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)`). `codewizard-sherpa` is `pyproject.toml -> license = { text = "Proprietary" }`. **HARD INCOMPATIBILITY.** This blocker alone disqualifies `pyarn` independent of every other criterion.
- **Verified `pyarn` API surface (per AC-13):** `pyarn.lockfile.Lockfile.from_str(lockfile_str) -> Lockfile`; the parsed dict is `Lockfile.data` (`dict[str, dict[str, Any]]` keyed by raw entry header). The `_pyarn_parse(body: bytes) -> YarnLock` adapter in `_yarn.py` calls `Lockfile.from_str(body.decode("utf-8"))` and casts `lock.data` into `YarnLock["entries"]`. Recorded for the case where a future revision of this ADR (a) re-licenses `pyarn` permissively or (b) re-licenses `codewizard-sherpa` GPL-compatible — the adapter is ready.

**Rationale (one sentence):** The license incompatibility is a hard blocker (Rule 12: a "close call" is a decision, not a deferral); the borderline release-age (15 days outside the freshness window) reinforces the decision per Notes-for-implementer §13 ("default to hand-rolled and document the borderline decision"); the hand-rolled scanner is ~80 lines of pure-Python state-machine code with no regex over the full body, locally fuzz-tested per AC-16 before this PR.

**Consequences for `pyproject.toml`:** `pyarn` is **not** added to `[project.optional-dependencies] gather` (AC-14). The `_pyarn_parse` adapter still ships behind `_HAS_PYARN: bool`, so a developer who manually `pip install pyarn` locally for parity-test work in S3-04 picks up the dispatch automatically. The S3-04 parity test installs `pyarn` in a CI-only matrix slot per its own ADR.

**Reversibility:** A future revision flipping this selection to `pyarn` is mechanically `pip install pyarn` (which flips `_HAS_PYARN` via `find_spec`) plus this ADR's land-time block being amended; the wire contract (`YarnLock` `TypedDict`) is parser-agnostic. The license blocker would need an independent resolution (either upstream re-license or a fork under a permissive license).

**Evidence:**

- `tests/unit/probes/_lockfiles/test_yarn.py::test_adr_0003_land_time_selection_block_is_filled` — pins the dated header pattern in this ADR text.
- `tools/fuzz_yarn_lock.py` (S3-03 AC-16) — local 1000-iteration byte-mutation fuzz of `_parse_handrolled`; worst-case wall-clock pasted in PR body.
- `_lockfiles/_yarn.py` — `_PARSER_KIND: Final[str] = "yarn_lockfile"` discriminates the cap-exceeded event for downstream observability per the registry pattern.
