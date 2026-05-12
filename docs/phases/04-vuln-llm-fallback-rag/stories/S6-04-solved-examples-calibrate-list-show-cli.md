# Story S6-04 — `codegenie solved-examples calibrate | list | show` CLI

**Step:** Step 6 — Ship synchronous gated `writeback_solved_example` + Gap-4 semantics + operator CLI
**Status:** Ready
**Effort:** S
**Depends on:** S6-03 (orchestrator wired; the corpus is provably non-empty for an exit-criterion run; `RunConfig` shape final)
**ADRs honored:** ADR-P4-015 (`SolvedExample` v0.4.0 schema — `list` / `show` round-trip the canonical schema), ADR-P4-002 (`merge_status` lifecycle is human-visible; `--merge-status` filter exposes it), ADR-P4-005 (chromadb in-process — `list` queries the embedded store, not a server), NG8 ("`solved-examples calibrate` suggest-only, never auto-write") — surfaced in the open-questions ledger under #5 (`final-design.md §"Open questions"`)

## Context
With S6-03 the corpus grows and the orchestrator records the writebacks. This story ships the operator-facing inspection + calibration surface inside the existing `codegenie solved-examples` subcommand group (stubbed in S1-06, partially wired with `reindex` / `prune` / `health` in S4-07). Three new subcommands:

- `codegenie solved-examples calibrate` — sweeps the `τ_hit` / `τ_few` retrieval thresholds against the **labeled fixture set** from `tests/fixtures/rag/labeled/` (the same set S7-01 builds for the recall@3 canary), computes a misclassification ROC, **suggests** new thresholds via stdout, **writes** them to `.codegenie/calibration-<utc>.yaml` in the workspace, **does not** auto-write to `~/.config/codegenie/llm.yaml`. The operator copies the suggestion across by hand. NG8 / ADR-P4-006 documents this as "humans-in-the-loop on threshold drift" — the same discipline as production ADR-0009 applied to a different decision surface.
- `codegenie solved-examples list [--cve <id>] [--merge-status <status>] [--collection <pending|promoted|negative>]` — pages over the corpus, prints a one-line-per-example table (`id`, `task_class`, `cve`, `created_at`, `merge_status`, `plan_source`, `cost_usd`).
- `codegenie solved-examples show <example_id>` — full body JSON + `Provenance` + linked audit chain head; pretty-prints for human review.

All three are read-only (calibrate writes a workspace file, not config). Phase 11 will add `promote <id> --merge-sha ... --reviewer ...` as a sibling subcommand — the API shape is already committed in arch §8, so this story plants the subcommand-group registrations Phase 11 will extend without edits.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §"Operator-facing surfaces"` — the full `codegenie solved-examples {list,show,promote,prune,health,calibrate}` matrix; this story ships `list`, `show`, `calibrate` (the last three of the six; `health` is S4-06, `prune --orphans` and `reindex` are S4-07; `promote` is Phase 11).
  - `../phase-arch-design.md §"Component design" #8` — `SolvedExampleStore.query(...)` is the read path for `list`; `SolvedExampleStore.health()` ships for `health` (out of scope here).
  - `../phase-arch-design.md §"Open questions" #5` — `solved-examples calibrate` auto-write vs suggest-only — synth picks suggest-only (NG8); this story instantiates the decision.
  - `../phase-arch-design.md §"Open questions" #8` — Phase 4 + Phase 11 promotion-rollback (the `delete <id>` recall path is forecast; first arises here).
  - `../phase-arch-design.md §"Edge cases"` row EC4 — chromadb open failure makes `list` fail loud (exit 11, `config_invalid`) rather than silently empty.
- **Phase ADRs:**
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — `list` / `show` consume v0.4.0 schema; `show` round-trips the body file.
  - `../ADRs/0002-two-tier-writeback-pending-promoted.md` — ADR-P4-002 — `--merge-status` filter exposes the `pending_human` / `merged` / `withdrawn` lifecycle.
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — calibration sweep uses the current `EmbeddingProvider.model_digest`; the suggestion is only valid against that digest.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — production ADR-0009 — the writeback config is human-managed for the same reason the merge is human-managed.
- **Source design:**
  - `../final-design.md §"Open questions" #5` — calibration shape.
  - `../final-design.md §"Open questions" #8` — Phase 11 rollback.
- **Existing code:**
  - `src/codegenie/cli.py` (S1-06) — the `solved-examples` subcommand group exists as `--help` stub; this story fills three commands.
  - `src/codegenie/rag/store.py` (S4-04) — `store.read().query(...)`, `store.health()`, body-file path resolution.
  - `src/codegenie/rag/models.py` (S1-03) — `SolvedExample`, `Provenance`.
  - `src/codegenie/cli.py` exit-code map (S1-06) — `9` (operational refusal), `10` (LLM upstream), `11` (config invalid).
  - `tests/fixtures/rag/labeled/` (S7-01) — the labeled-triple fixture set the calibration sweep reads. **Important:** S7-01 is downstream; if this story lands before S7-01 (it shouldn't per the manifest), the calibration test uses a small inline fixture and S7-01 swaps it in.

## Goal
Ship three `solved-examples` subcommands (`calibrate` suggest-only-to-workspace, `list` with three filters, `show <id>` round-trip) that round-trip the v0.4.0 schema, write nothing to `~/.config/codegenie/`, and exit cleanly when the store is empty or corrupted.

## Acceptance criteria
- [ ] `codegenie solved-examples calibrate` is wired:
  - Reads the labeled fixture set from `tests/fixtures/rag/labeled/*.yaml` (S7-01 owns the corpus; this story is the consumer). Each fixture is `(advisory, repo_fingerprint, expected_top1_example_id)`.
  - Sweeps `τ_hit ∈ {0.80, 0.82, 0.84, 0.86, 0.88, 0.90}` × `τ_few ∈ {0.68, 0.70, 0.72, 0.74, 0.76}` against the labeled set; computes for each pair: `(true_hits, false_hits, true_fewshot, false_fewshot, true_cold, false_cold)` and a single F1 score against the labels.
  - Prints to stdout the top-3 `(τ_hit, τ_few)` candidates by F1, each with its precision/recall and a recommended action ("RAISE τ_hit from 0.86 to 0.88 to reduce misleading-match rate by 12%").
  - Writes the **full sweep** to `.codegenie/calibration-<utc-iso8601>.yaml` in the workspace (the analyzed repo's `.codegenie/`); structure includes the parameter sweep table, the labeled-set size, the current thresholds, and the `embedding_model_digest` at calibration time.
  - **Does not** write to `~/.config/codegenie/llm.yaml`. **Does not** write to `~/.config/codegenie/anything-else`.
  - Exit 0 on success; exit 11 if the labeled-set is empty (advise operator); exit 9 if the embedding model's `model_digest` doesn't match the digests recorded in the corpus rows (a calibration across model swaps is meaningless — refuse loudly).
- [ ] `tests/integration/test_solved_examples_calibrate.py` — runs `calibrate` against a fixture corpus of ~10 examples + ~10 labeled queries; asserts:
  1. stdout includes the top-3 candidate suggestions in human-readable form (regex match on the table shape).
  2. `.codegenie/calibration-<utc>.yaml` exists after the run, contains the full sweep, parses as YAML.
  3. `~/.config/codegenie/llm.yaml` is **unmodified** byte-for-byte (snapshot `stat` + content before/after).
  4. Exit code 0.
  5. Re-running shows a new `.codegenie/calibration-<utc>.yaml` file (timestamps differ); the previous one is left in place (operators can compare across runs).
- [ ] `tests/integration/test_solved_examples_calibrate_empty_fixture.py` — empty labeled set → exit 11 with stderr message pointing operators at the fixture path; no calibration file written.
- [ ] `tests/integration/test_solved_examples_calibrate_digest_mismatch.py` — corpus rows carry a different `embedding_model_digest` than the current `EmbeddingProvider.model_digest` → exit 9 with stderr noting the mismatch and suggesting `solved-examples reindex` (the S4-07 recovery path); no calibration file written.
- [ ] `codegenie solved-examples list` is wired:
  - Flags: `--cve <id>` (filter by `advisory.canonical_id` substring or exact), `--merge-status <pending_human|merged|withdrawn|all>` (default `all`), `--collection <pending|promoted|negative|all>` (default `all`).
  - Output: one row per example to stdout in tabular form (columns: `id` (12-char prefix), `cve`, `task_class`, `created_at`, `merge_status`, `plan_source`, `cost_usd`). Sortable by `created_at` desc (most recent first).
  - Pages at 50 rows; appends `... <N more> — pass --limit <N> to widen` when truncated.
  - Exit 0 on success (even with zero matches — empty is not error); exit 11 if the store is corrupted (chromadb open failure surfaces here loudly).
- [ ] `tests/integration/test_solved_examples_list_show.py` — seeds the store with three examples spanning all three collections (`pending`, `promoted`, `negative`); runs:
  1. `list` with no filters → all three visible.
  2. `list --collection promoted` → only the promoted one.
  3. `list --merge-status pending_human` → only the pending one.
  4. `list --cve CVE-2024-X` → only matching rows.
  5. `show <example_id>` → stdout contains the body JSON + provenance + audit chain head.
  Round-trip assertion: `show` output parses as JSON, validates as `SolvedExample` (Pydantic), and `example.id == <example_id>`.
- [ ] `codegenie solved-examples show <example_id>` is wired:
  - Reads the body JSON from `.codegenie/rag/bodies/<id>.json`, pretty-prints it (`json.dumps(indent=2, sort_keys=False)`) to stdout, with a header showing `merge_status`, `created_at`, `audit_chain_head`, `embedding_model`, `plan_source`.
  - Round-trips through `SolvedExample.model_validate_json(...)` before printing (any schema violation surfaces as exit 11).
  - Exit 0 on success; exit 11 if the id is malformed or the body file is missing (chromadb has a row but the body is orphaned → also suggest `prune --orphans`).
- [ ] `tests/integration/test_solved_examples_show_orphan_body.py` — corpus row exists but body file is missing → exit 11; stderr suggests `solved-examples prune --orphans` (S4-07).
- [ ] `tests/unit/cli/test_solved_examples_subcommands_registered.py` — `codegenie solved-examples --help` lists `calibrate`, `list`, `show` alongside the existing `health`, `prune`, `reindex`. The `promote` subcommand is **not** listed (Phase 11). The output is snapshot-tested so a Phase-11 addition is conspicuous.
- [ ] `tests/unit/cli/test_calibrate_does_not_modify_user_config.py` — patches `pathlib.Path.write_text` / `os.replace` to **fail loud** if any call site under `~/.config/codegenie/` is touched during a `calibrate` run; the patch is in the test, not the SUT — the test fails if production code writes to user config. (NG8 enforcement.)
- [ ] `tests/unit/cli/test_calibrate_workspace_yaml_shape.py` — round-trips the `.codegenie/calibration-<utc>.yaml` file through a Pydantic `CalibrationReport` model (`extra="forbid"`); golden YAML fixture under `tests/golden/calibration/calibration_report.yaml`.
- [ ] `CalibrationReport` Pydantic model exists (`src/codegenie/rag/calibration.py` or `src/codegenie/cli/calibrate.py`) with `extra="forbid", frozen=True`; contract-snapshot test `tests/contracts/test_calibration_report_snapshot.py` freezes the shape so a Phase 5+ extension is conspicuous.
- [ ] `mypy --strict`, `ruff check`, `ruff format --check` clean on every touched file; CLI help text covered by a snapshot test (`tests/unit/cli/test_solved_examples_help_snapshot.py`) so wording drift is caught.

## Implementation outline
1. Add module `src/codegenie/cli/solved_examples.py` (or extend the existing module from S1-06) with three click subcommands: `calibrate`, `list`, `show`. Register them in the `solved-examples` group.
2. `calibrate` implementation:
   - Load labeled fixtures via a helper (`_load_labeled_set() -> list[LabeledQuery]`) reading `tests/fixtures/rag/labeled/*.yaml` (the path is configurable via `--fixtures-dir`, default to the project-relative path; this lets S7-01 swap the corpus in without touching the SUT).
   - Pre-flight: check `EmbeddingProvider.model_digest` against the corpus's most-recent-row `embedding_model_digest`; mismatch → exit 9.
   - Sweep loop (deterministic order): for each `(τ_hit, τ_few)` pair, simulate `RagLlmEngine._plan_from_rag`'s decision against each labeled query (this is *pure* — no LLM, no embedding compute beyond what the corpus already has); tally outcomes; compute F1.
   - Sort, print top-3 to stdout, write full sweep to `.codegenie/calibration-<utc>.yaml`.
3. `list` implementation:
   - Open `store.read()` (shared flock per S4-04).
   - Apply filters in-memory (the corpus is small; for 1k examples this is < 50 ms). Sort by `created_at` desc. Truncate at `--limit` (default 50).
   - Use `rich.table.Table` or a hand-rolled aligned-column printer for stdout. No dependencies beyond what S1-06 already imported.
4. `show` implementation:
   - Resolve body path: `.codegenie/rag/bodies/<id>.json`. If missing, exit 11 with the `prune --orphans` hint.
   - Read, `SolvedExample.model_validate_json(...)`, pretty-print with the header.
5. Help text: each subcommand carries a one-paragraph docstring referencing the relevant ADR (`calibrate` → ADR-P4-006 + NG8; `list` → ADR-P4-002; `show` → ADR-P4-015). The snapshot test pins these.
6. Phase-11 forecast: leave a registered-but-unimplemented `promote` stub (or, simpler, *no* stub — Phase 11 can add it cleanly). Pick "no stub" — adding stubs to ship clean help text is gold-plating. The snapshot test asserts `promote` is **not** present in Phase 4.

## TDD plan — red / green / refactor

### Red
Test file path: `tests/integration/test_solved_examples_calibrate.py`
```python
from pathlib import Path
import yaml
from click.testing import CliRunner
from codegenie.cli import cli


def test_calibrate_suggests_thresholds_writes_workspace_only(tmp_path, monkeypatch):
    """NG8: calibrate suggests new thresholds via stdout + .codegenie/, never auto-writes user config."""
    user_config = tmp_path / "config" / "codegenie" / "llm.yaml"
    user_config.parent.mkdir(parents=True)
    original_bytes = b"# original config — should not be modified\nllm:\n  tau_hit: 0.86\n  tau_few: 0.72\n"
    user_config.write_bytes(original_bytes)
    monkeypatch.setenv("HOME", str(tmp_path))

    workspace = tmp_path / "repo"
    workspace.mkdir()
    _seed_corpus(workspace, examples=10, labeled_queries=10)

    runner = CliRunner()
    result = runner.invoke(cli, ["solved-examples", "calibrate", "--repo", str(workspace)])

    assert result.exit_code == 0, result.output + result.stderr
    # stdout includes the top-3 suggestions
    assert "RAISE" in result.output or "LOWER" in result.output or "KEEP" in result.output
    # workspace file exists
    cal_files = list((workspace / ".codegenie").glob("calibration-*.yaml"))
    assert len(cal_files) == 1
    sweep = yaml.safe_load(cal_files[0].read_text())
    assert "tau_hit_sweep" in sweep and "tau_few_sweep" in sweep
    assert sweep["embedding_model_digest"]
    # user config UNCHANGED — NG8 + ADR-P4-006
    assert user_config.read_bytes() == original_bytes
```

`tests/unit/cli/test_calibrate_does_not_modify_user_config.py`
```python
def test_calibrate_never_writes_under_user_config(tmp_path, monkeypatch):
    """Defence-in-depth: even a bug that tries to write user config must surface as a CI red."""
    writes: list[Path] = []
    orig_write_text = Path.write_text
    orig_replace = __import__("os").replace

    def _trace_write_text(self, *a, **kw):
        if str(self).startswith(str(tmp_path / "config" / "codegenie")):
            writes.append(self)
        return orig_write_text(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", _trace_write_text)
    monkeypatch.setenv("HOME", str(tmp_path))

    # ... run calibrate ...

    assert writes == [], f"calibrate wrote to user config: {writes}"
```

`tests/integration/test_solved_examples_list_show.py`
```python
def test_list_show_roundtrip(tmp_path):
    _seed_three_examples(tmp_path, pending=1, promoted=1, negative=1)
    runner = CliRunner()

    r_all = runner.invoke(cli, ["solved-examples", "list", "--repo", str(tmp_path)])
    assert r_all.exit_code == 0
    assert r_all.output.count("\n") >= 3  # at least three rows

    r_pending = runner.invoke(cli, ["solved-examples", "list", "--collection", "pending", "--repo", str(tmp_path)])
    assert "pending_human" in r_pending.output
    assert "merged" not in r_pending.output

    example_id = _seeded_pending_id(tmp_path)
    r_show = runner.invoke(cli, ["solved-examples", "show", example_id, "--repo", str(tmp_path)])
    assert r_show.exit_code == 0
    # round-trip the body through the schema
    body_json = _extract_json_body(r_show.output)
    example = SolvedExample.model_validate_json(body_json)
    assert example.id == example_id
```

### Green
- Land three click subcommands; wire `calibrate` to read labeled fixtures, run the sweep, print + write workspace YAML; wire `list` to filter + tabulate `store.read().query(...)`; wire `show` to round-trip `SolvedExample` from disk.
- Implement `_pure_plan_from_rag(τ_hit, τ_few, cosine, plan_kind)` — extracted from `RagLlmEngine._plan_from_rag` (S5-02) — so the calibration sweep can simulate decisions without invoking the engine. Re-use rather than reimplement (a separate `_plan_from_rag` invites drift).

### Refactor
- Move the threshold-sweep logic into `src/codegenie/rag/calibration.py` as `CalibrationSweep` (input: corpus + labeled set; output: `CalibrationReport`); the CLI command is then a thin wrapper. This keeps the CLI module under 200 LOC and makes the sweep unit-testable in isolation.
- Add a structured `cli.solved_examples.calibrate.run` audit event (one per invocation, includes `top1_suggestion`, `current_thresholds`, `embedding_model_digest`); audit chain extension per `phase-arch-design.md §"Audit chain extension"` if not already on the list.
- Edge cases: corpus has zero rows (`calibrate` exits 11 with "seed the corpus first"); user config missing (`calibrate` still works — it doesn't read user config, only writes are forbidden); user runs `calibrate` repeatedly (each run creates a new timestamped file; no GC — operators decide).
- Help-text snapshot: pin both the group's `--help` and each subcommand's `--help` so the wording is a contract.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/cli/solved_examples.py` | NEW (or extend the existing module) — three click subcommands. |
| `src/codegenie/rag/calibration.py` | NEW — `CalibrationSweep`, `CalibrationReport` Pydantic. |
| `src/codegenie/cli.py` | Register the three subcommands under the `solved-examples` group. |
| `tests/integration/test_solved_examples_calibrate.py` | NEW |
| `tests/integration/test_solved_examples_calibrate_empty_fixture.py` | NEW |
| `tests/integration/test_solved_examples_calibrate_digest_mismatch.py` | NEW |
| `tests/integration/test_solved_examples_list_show.py` | NEW |
| `tests/integration/test_solved_examples_show_orphan_body.py` | NEW |
| `tests/unit/cli/test_solved_examples_subcommands_registered.py` | NEW |
| `tests/unit/cli/test_calibrate_does_not_modify_user_config.py` | NEW — NG8 defence-in-depth. |
| `tests/unit/cli/test_calibrate_workspace_yaml_shape.py` | NEW — `CalibrationReport` round-trip. |
| `tests/unit/cli/test_solved_examples_help_snapshot.py` | NEW — help-text snapshot. |
| `tests/contracts/test_calibration_report_snapshot.py` | NEW — `CalibrationReport` schema dump. |
| `tests/golden/calibration/calibration_report.yaml` | NEW — golden fixture. |

## Out of scope
- **`codegenie solved-examples promote <id> --merge-sha ... --reviewer ...`** — Phase 11 territory. Production ADR-0009 says humans always merge; Phase 4 ships only the `merge_status="pending_human"` writeback path. The arch §8 API is fixed; Phase 11 lands the click subcommand.
- **`codegenie solved-examples delete <id>` (the rollback path)** — `final-design.md §"Open questions" #8` flags this for Phase 16 hardening, not Phase 4.
- **Automatic `~/.config/codegenie/llm.yaml` writing** — explicitly forbidden by NG8 / ADR-P4-006. The test `test_calibrate_does_not_modify_user_config` is the durable enforcement.
- **`codegenie solved-examples health`** — handled by S4-06 (the probe ships there).
- **`codegenie solved-examples prune --orphans` / `reindex`** — handled by S4-07.
- **Negative-example collection writes** — Phase 4 forbids them entirely (G4); `list --collection negative` shows an empty collection in Phase 4. Phase 15's recipe-authoring lens may reopen.

## Notes for the implementer
- **NG8 is the load-bearing rule.** A reviewer who suggests "let's just write the new thresholds to `~/.config/codegenie/llm.yaml` for the operator's convenience" is exactly what production ADR-0009 forbids on a different decision surface. The two `tests/unit/cli/test_calibrate_does_not_modify_user_config` tests (the integration one + the defence-in-depth one) are both required.
- **Calibration is a *pure* simulation.** The sweep does not invoke the LLM, does not embed anything new, does not query the live store beyond reading cosines that are already recorded in chromadb metadata. This is what makes calibration fast (< 5s on 1k examples) and deterministic.
- **Embedding-model-digest mismatch is a refusal, not a warning.** Calibrating across a digest swap produces meaningless suggestions (the cosine distribution has changed). Refuse loudly with exit 9 and point the operator at `solved-examples reindex` (S4-07).
- **`list` truncation discipline.** Default `--limit 50` is enough for human inspection; operators who want the full corpus dump can pipe through `--limit 100000`. Do not page interactively — that's a separate UX surface that doesn't belong in Phase 4.
- **`show` round-trips through Pydantic.** If a body file on disk fails schema validation, that's a corpus corruption signal — exit 11 with the body path + the validation error. The operator's recovery path is `prune --orphans` (for missing bodies) or filing a bug (for malformed bodies — Phase 4 writes are schema-validated, so a malformed body suggests external tampering or a future-version schema migration in progress).
- **Phase 11 hand-off cleanliness.** The `promote` subcommand is intentionally absent in Phase 4. Phase 11 will add it as a sibling under the same group; the snapshot test catches any premature addition. The arch §8 signature is fixed (`promote(example_id, *, reason, merge_sha=None, reviewer=None)`), so Phase 11's CLI command is a straight click-wrapper on the existing method.
- **Help-text snapshots feel pedantic; they're not.** A future docs writer rephrasing a help string can silently break operator runbooks (e.g. `phase-arch-design.md §"Operator-facing surfaces"` quotes a specific phrase). The snapshot catches the drift before merge.
- **Coverage floor is 90/80 on `src/codegenie/cli/solved_examples.py` and 95/90 on `src/codegenie/rag/calibration.py` (the calibration math).** The math is the more important half: a one-character bug in the sweep produces silently-wrong threshold suggestions. Write the unit tests for `CalibrationSweep` separately from the CLI integration tests — the math wants property-based coverage, not just one happy-path example.
