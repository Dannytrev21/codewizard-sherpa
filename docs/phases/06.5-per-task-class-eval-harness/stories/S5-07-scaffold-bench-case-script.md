# Story S5-07 — `scripts/scaffold_bench_case.py` operator tool

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** Ready
**Effort:** S
**Depends on:** S5-01 (the directory contract + `BenchCase` schema must exist before the scaffolder knows what to emit)
**ADRs honored:** ADR-0006 (the scaffolder asks for `--curation-class` so the resulting case carries the right Literal); ADR-0005 (the scaffolder mints a 32-hex `cassette_canary_pin`); ADR-0004 + ADR-0008 are honored *transitively* — the scaffolder does not author `breakdown_keys.py` or `failure_modes.yaml` (those are per-task-class, not per-case)

## Context

`bench/vuln-remediation/`'s 10-case floor is the long-pole curation work in the phase (`High-level-impl.md §Implementation-level risks #1`). Hand-writing a `case.toml` from memory — all required fields, the right Literal values, a freshly-minted pin, a BLAKE3 digest — is mechanical and error-prone. Open Question #8 in the architecture (`phase-arch-design.md §Open questions deferred to implementation`) calls out the bench-author bootstrap experience as a gap: there is no operator tool. This story closes it.

The scaffolder is deliberately small: it takes a task-class slug + a CVE identifier (or arbitrary slug) + a curation-class, lays down the case directory skeleton with a stubbed `case.toml`, empty `input/` and `expected/` placeholders, a freshly-minted pin, and emits a `digests.yaml` patch line the curator can copy into the signing file once `input/`/`expected/` are populated. The point is to remove every avoidable curation error, not to *do* the curation (which remains a human judgment).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §`bench/{task-class}/` directory contract` — the precise `case.toml` schema this script must emit.
  - `../phase-arch-design.md §Open questions deferred to implementation §OQ #8` — names this script as the operator-bootstrap remediation.
  - `../phase-arch-design.md §Data model → BenchCase` — required fields with their Literal-valued constraints.
- **Phase ADRs:**
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Consequences` — naming convention `001-005-rag-corpus-derived-*` / `006-010-held-out-*` (advisory).
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §Decision` — the 32-hex pin shape; `Canary.mint()` is the Phase 4 entry point (amended in S7-03).
- **Source design:** `../High-level-impl.md §Step 5` Features delivered → "`scripts/scaffold_bench_case.py` (Open Q #8) — operator tooling for `--task-class` + `--cve` → scaffolded case directory".

## Goal

Land `scripts/scaffold_bench_case.py` as an operator CLI that takes `--task-class`, `--cve` (or `--slug`), `--curation-class`, and optional `--source-cassette`, and writes a structurally-valid `bench/<task-class>/cases/<case-id>/` skeleton with a stub `case.toml` (all required fields filled with valid Literal values), empty `input/` + `expected/` directories, and prints a ready-to-paste `digests.yaml` entry.

## Acceptance criteria

- [ ] `scripts/scaffold_bench_case.py` exists; running `python scripts/scaffold_bench_case.py --help` prints usage including `--task-class`, `--cve`, `--slug`, `--curation-class`, `--source-cassette`, `--bench-root`, `--dry-run`.
- [ ] Running `python scripts/scaffold_bench_case.py --task-class=vuln-remediation --cve=CVE-2025-99999 --curation-class=held-out` creates `bench/vuln-remediation/cases/0XX-cve-2025-99999-held-out/{case.toml, input/.gitkeep, expected/.gitkeep}` where `0XX` is the next available zero-padded index (looks at existing cases under `bench/<task-class>/cases/`).
- [ ] The emitted `case.toml` validates into a `BenchCase` when `input/` and `expected/` are populated — every required field is present with a valid Literal/typed value; the `case_digest` is initially set to `"blake3:0000...0000"` with a `# REPLACE: compute via scripts/sign_bench_digests.py after populating input/ and expected/` comment.
- [ ] The emitted `cassette_canary_pin` is a freshly-minted 32-hex string (deterministic per case_id for reproducibility — derive as `blake3(f"{task_class}/{case_id}".encode()).hexdigest()[:32]` if `Canary.mint(seed=)` is unavailable; or pass through to it if S2-05 has landed).
- [ ] The script emits a stdout block titled "Next steps:" naming: (1) populate `input/`; (2) populate `expected/`; (3) run `python scripts/sign_bench_digests.py --task-class=vuln-remediation`; (4) commit. The block is bench-author friendly — not just a "you're done" message.
- [ ] If a case with the same `case_id` already exists, the script exits non-zero (1) with a diagnostic naming the existing path; the script never overwrites existing cases.
- [ ] `--dry-run` prints the would-be `case.toml` to stdout and creates nothing.
- [ ] `--source-cassette=<path>` (used by S5-03's RAG-corpus-derived workflow) adds a `# Derived from: <path>` comment block at the top of `case.toml` and (optionally) emits `input/`/`expected/` files copied from the cassette structure.
- [ ] `--curation-class=held-out` is rejected if no `--cve` is provided (held-out cases must carry CVE identifiers per ADR-0006 §Consequences); the diagnostic explains why.
- [ ] Red test from §TDD plan exists, was committed at red, now green; `ruff check`, `ruff format --check`, `mypy --strict scripts/scaffold_bench_case.py`, `pytest tests/unit/test_scaffold_bench_case.py` all pass.

## Implementation outline

1. Write the red test `tests/unit/test_scaffold_bench_case.py` first — see §TDD plan.
2. Implement `scripts/scaffold_bench_case.py` using `click` (consistent with `codegenie` CLI style — see `phase-arch-design.md §Component design → src/codegenie/eval/cli.py`). Keep it under ~200 LOC; this is operator tooling, not a framework.
3. The CLI signature:
   ```python
   @click.command()
   @click.option("--task-class", required=True)
   @click.option("--cve", default=None, help="CVE-YYYY-NNNNN; required for held-out")
   @click.option("--slug", default=None, help="alternative slug if --cve unavailable")
   @click.option("--curation-class", type=click.Choice(["rag-corpus-derived", "held-out"]), required=True)
   @click.option("--source-cassette", type=click.Path(exists=True, path_type=Path), default=None)
   @click.option("--bench-root", type=click.Path(path_type=Path), default=Path("bench"))
   @click.option("--dry-run", is_flag=True)
   def main(task_class, cve, slug, curation_class, source_cassette, bench_root, dry_run): ...
   ```
4. Index allocation: walk `bench/<task-class>/cases/` for existing `NNN-*` directories; pick the next available 3-digit index.
5. case_id construction: `f"{index:03d}-{cve.lower() if cve else slug}-{curation_class}"` (lowercased CVE; preserve slug case if user passed it lowercase).
6. case.toml emission: use a Python f-string or `tomli_w` for safety. Include every required field. The `added_at` and `last_validated_at` are `datetime.now(UTC).isoformat()`.
7. `digests.yaml` patch line: print to stdout: `# Add this line to bench/<task-class>/cases/digests.yaml after populating input/ and expected/:\n<case_id>: <case_digest>`.
8. Iterate test → green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_scaffold_bench_case.py`

```python
# tests/unit/test_scaffold_bench_case.py
"""Operator tool for scaffolding bench cases. Open Q #8 closure."""

import subprocess
import sys
from pathlib import Path

import pytest
import tomllib


SCRIPT = Path(__file__).parents[2] / "scripts" / "scaffold_bench_case.py"


def _run(args, cwd=None, check=False):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd, check=check,
    )


def test_help_lists_required_and_optional_flags():
    r = _run(["--help"])
    assert r.returncode == 0
    for flag in ("--task-class", "--cve", "--slug", "--curation-class",
                 "--source-cassette", "--bench-root", "--dry-run"):
        assert flag in r.stdout, f"missing flag in --help: {flag}"


def test_scaffolds_held_out_case_with_cve_into_correct_directory(tmp_path):
    bench = tmp_path / "bench"
    (bench / "vuln-remediation" / "cases").mkdir(parents=True)
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode == 0, r.stderr
    case_dir = bench / "vuln-remediation" / "cases" / "001-cve-2025-99999-held-out"
    assert case_dir.is_dir()
    assert (case_dir / "case.toml").is_file()
    assert (case_dir / "input").is_dir()
    assert (case_dir / "expected").is_dir()


def test_emitted_case_toml_has_all_required_fields_with_valid_literals(tmp_path):
    bench = tmp_path / "bench"
    (bench / "vuln-remediation" / "cases").mkdir(parents=True)
    _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ], check=True)
    toml = tomllib.loads(
        (bench / "vuln-remediation" / "cases" / "001-cve-2025-99999-held-out" / "case.toml").read_text()
    )
    assert toml["case_id"] == "001-cve-2025-99999-held-out"
    assert toml["task_class"] == "vuln-remediation"
    assert toml["curation_class"] == "held-out"
    assert toml["disposition"] in {"positive", "negative", "ambiguous"}
    assert toml["difficulty"] in {"easy", "medium", "hard"}
    assert toml["source"] in {"curated", "outcome-ledger-derived", "regression-converted"}
    assert len(toml["cassette_canary_pin"]) == 32
    assert all(c in "0123456789abcdef" for c in toml["cassette_canary_pin"])
    assert toml["case_digest"].startswith("blake3:")


def test_next_index_increments_past_existing_cases(tmp_path):
    bench = tmp_path / "bench"
    cases_root = bench / "vuln-remediation" / "cases"
    cases_root.mkdir(parents=True)
    for i in range(1, 4):
        (cases_root / f"{i:03d}-fake-rag-corpus-derived").mkdir()
    _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-44444",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ], check=True)
    assert (cases_root / "004-cve-2025-44444-held-out").is_dir()


def test_held_out_requires_cve_identifier(tmp_path):
    bench = tmp_path / "bench"
    (bench / "vuln-remediation" / "cases").mkdir(parents=True)
    r = _run([
        "--task-class=vuln-remediation",
        "--slug=just-a-slug",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode != 0
    assert "cve" in (r.stderr + r.stdout).lower()


def test_dry_run_prints_case_toml_and_creates_nothing(tmp_path):
    bench = tmp_path / "bench"
    (bench / "vuln-remediation" / "cases").mkdir(parents=True)
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
        "--dry-run",
    ])
    assert r.returncode == 0
    assert "case_id" in r.stdout  # printed the TOML
    assert not list((bench / "vuln-remediation" / "cases").iterdir())


def test_collision_with_existing_case_id_fails(tmp_path):
    bench = tmp_path / "bench"
    cases = bench / "vuln-remediation" / "cases"
    cases.mkdir(parents=True)
    (cases / "001-cve-2025-99999-held-out").mkdir()  # pre-existing collision
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    # Either next-index allocation steps over (002-...) OR fail. Decision:
    # next-index allocates 002; the test asserts the non-overwrite behavior.
    assert (cases / "001-cve-2025-99999-held-out").exists()
    # New case lives at next index OR script refused; either way no overwrite.
    assert r.returncode == 0 or "already exists" in (r.stderr + r.stdout).lower()


def test_stdout_includes_next_steps_block(tmp_path):
    bench = tmp_path / "bench"
    (bench / "vuln-remediation" / "cases").mkdir(parents=True)
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ], check=True)
    assert "next step" in r.stdout.lower()
    assert "sign_bench_digests" in r.stdout
```

Run; expect `FileNotFoundError` on the script. Commit as red marker.

### Green — smallest impl shape

1. Implement the script with click; emit the TOML via `tomli_w` (or a careful f-string). Use `blake3` for the deterministic pin derivation if Phase 4 `Canary.mint(seed=)` isn't available yet.
2. Index allocation: `max([int(p.name[:3]) for p in cases_root.iterdir() if p.name[:3].isdigit()], default=0) + 1`.
3. The "Next steps" block is a print statement; keep it short and accurate.
4. Iterate until all 8 test functions pass.

### Refactor — clean up

- Module docstring cites `phase-arch-design.md §OQ #8` as the rationale.
- Click help text for each flag explains the constraint (`--cve` "required for held-out per ADR-0006"; `--curation-class` "chooses ADR-0006 split"; etc.).
- The emitted `case.toml` carries a top-of-file comment block: `# Generated by scripts/scaffold_bench_case.py at <ISO timestamp>\n# Populate input/ and expected/, then run scripts/sign_bench_digests.py\n# ADRs: ADR-0006 (curation class), ADR-0005 (canary pin), ADR-0004 (failure modes)\n`.
- A `--list-task-classes` flag (small bonus) prints the registered task classes from `default_registry` for discoverability — mark "out of scope unless trivial".
- Coverage: aim for ≥ 85% line on the script; mypy `--strict` clean.

## Files to touch

| Path | Why |
|---|---|
| `scripts/scaffold_bench_case.py` | New — operator CLI |
| `tests/unit/test_scaffold_bench_case.py` | New — 8 structural assertions |
| `scripts/sign_bench_digests.py` (referenced) | Referenced by the "next steps" block; landed by S5-05; this story does not implement it but the message must point at it accurately |
| `bench/vuln-remediation/README.md` (optional) | Add a "Adding a new case" section pointing curators at `scripts/scaffold_bench_case.py` |

## Out of scope

- **Authoring `breakdown_keys.py` / `failure_modes.yaml`.** Those are per-task-class, owned by S5-01 (and analogous task-class stories). The scaffolder is per-case.
- **Computing the final `case_digest`.** The scaffolder emits a stub digest with a `REPLACE:` comment; `scripts/sign_bench_digests.py` (S5-05) is the actual signer.
- **Auto-extracting CVE metadata from public feeds.** A future enhancement; the current scaffold takes the CVE on the command line.
- **GUI / TUI.** The script is a CLI. The next step in operator UX is `codegenie eval scaffold-case` as a subcommand (deferred).
- **Wiring to Phase 4 cassette parsing.** `--source-cassette` accepts a path but does not deep-parse the cassette beyond copying its files. S5-03's RAG-corpus-derived workflow may add cassette-aware extraction in a follow-up.

## Notes for the implementer

- Keep it small. This is operator tooling, not a framework. ~150–200 LOC is the right size; if it grows past 300, something is off.
- The script's "Next steps" stdout block is the bench-author's UX. Wording matters: explicit, scannable, hyperlink-ish ("see ADR-0006" / "run `scripts/sign_bench_digests.py`"). Test asserts presence of key strings, not exact wording — give yourself room to tune copy.
- `tomli_w` (or `tomli` for reads, `tomllib` for stdlib reads ≥ Python 3.11) emits TOML. Avoid hand-rolled string concatenation for TOML — it's quote-escaping-trap territory.
- The deterministic-from-case-id pin derivation (`blake3(f"{task_class}/{case_id}".encode()).hexdigest()[:32]`) is **only** a fallback if Phase 4's `Canary.mint(seed=)` isn't yet wired. The amendment ADR (S2-05) ships the seed parameterization; once that's live, the scaffolder should call `Canary.mint(seed=os.urandom(16))` or similar to get a fresh non-derivable pin. For *now*, derivation-from-case-id is acceptable — document the fallback in the script.
- The script does not register the case with `default_registry`. Registration happens when the task-class loader walks `bench/<tc>/cases/`. The scaffolder just lays down files.
- If `--source-cassette` points to a directory, copy its `input.snapshot/` and `expected.snapshot/` (or analogous structure) into the new case's `input/` and `expected/`. If it points to a single file, copy it into `input/` only. The cassette structure is Phase 4's contract; depend on `tests/cassettes/phase4/<x>/README.md` if exists, else do a best-effort copy and let the curator clean up.
- Edge case: what if the curator runs the scaffolder before `bench/<task-class>/` exists? The script's `--bench-root` defaults to `bench`; if `bench/<task-class>/cases/` doesn't exist, the script should fail clearly ("`bench/<task-class>/` does not exist; run S5-01 first or pass an existing `--bench-root`"). Test for this behavior.
- This is operator tooling for the *project's curators*, not user-facing. Don't over-engineer error messages; do make them accurate. Curators are technical; they'll read tracebacks if needed.
