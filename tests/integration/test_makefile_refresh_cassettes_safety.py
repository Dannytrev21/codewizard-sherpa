"""S3-06 — safety + shape suite for `make refresh-cassettes`.

Each gate test runs `subprocess.run(..., env={"PATH": "/usr/bin:/bin"})` with a
minimal env so a contributor-local `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` shell
export cannot accidentally let a gate test "pass" by skipping the gate
(AC-14). Mutation guards are called out per test (Rule 9 — every test must
pin a specific wrong implementation it would catch).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIN_ENV = {"PATH": "/usr/bin:/bin"}
# Same shape as tests/unit/test_project_artifacts.py::GITHUB_USER_RE — handle
# or org/team. The runbook test below requires `fullmatch`.
OWNER_RE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9-]*(/[A-Za-z0-9._-]+)?$")


def _recipe_body(target: str, makefile: str) -> str:
    """Lines of a target's recipe (tab-indented), excluding the target line."""
    body: list[str] = []
    in_target = False
    for ln in makefile.splitlines():
        if ln.startswith(f"{target}:"):
            in_target = True
            continue
        if in_target:
            if ln.startswith("\t"):
                body.append(ln)
            elif ln.strip() == "":
                continue
            else:
                break
    return "\n".join(body)


# ---- gate: blocks without acknowledgement (AC-9, AC-14) --------------------


def test_refresh_cassettes_blocks_without_acknowledgement() -> None:
    """Mutation guard: an inverted / removed gate would let the recipe run -> not 2."""
    result = subprocess.run(
        ["make", "refresh-cassettes"],
        cwd=REPO_ROOT,
        env=MIN_ENV,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"expected 2 from un-ack'd refresh-cassettes; got {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "I_UNDERSTAND_THIS_SPENDS_TOKENS=1" in combined
    assert "ERROR" in combined


def test_refresh_gate_blocks_without_acknowledgement() -> None:
    """The pure gate target must block the same way the parent recipe does."""
    result = subprocess.run(
        ["make", "_refresh-cassettes-gate"],
        cwd=REPO_ROOT,
        env=MIN_ENV,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"expected 2 from un-ack'd gate; got {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "I_UNDERSTAND_THIS_SPENDS_TOKENS=1" in result.stdout + result.stderr


def test_refresh_gate_passes_with_acknowledgement_and_does_nothing_expensive() -> None:
    """Mutation guard: an `exit 2`-always gate makes refresh impossible and ships
    green against the block-test alone. The gate target must pass AND must NOT
    invoke pytest/record-mode (it is policy only — no token spend)."""
    result = subprocess.run(
        ["make", "_refresh-cassettes-gate", "I_UNDERSTAND_THIS_SPENDS_TOKENS=1"],
        cwd=REPO_ROOT,
        env=MIN_ENV,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"gate must pass with acknowledgement; got {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "ack-ok" in combined
    assert "pytest" not in combined and "record-mode" not in combined, (
        "the gate target must do ONLY the ack check — nothing expensive; "
        f"observed output:\n{combined}"
    )


# ---- recipe wiring: gate is a prerequisite, recipe does the work -----------


def test_refresh_cassettes_depends_on_gate() -> None:
    """Mutation guard: gate removal, or an expensive line slipped above it."""
    text = (REPO_ROOT / "Makefile").read_text()
    m = re.search(r"^refresh-cassettes:\s*(.+)$", text, flags=re.MULTILINE)
    assert m is not None, "refresh-cassettes target must exist"
    deps = m.group(1).split()
    assert "_refresh-cassettes-gate" in deps, (
        f"refresh-cassettes must list _refresh-cassettes-gate as a prerequisite; got {deps}"
    )


def test_refresh_recipe_records_and_rebuilds_lockfile() -> None:
    """Mutation guard: a recipe that drops --record-mode=all or the lock rebuild."""
    body = _recipe_body("refresh-cassettes", (REPO_ROOT / "Makefile").read_text())
    assert body, "refresh-cassettes must have a recipe body"
    assert "--record-mode=all" in body, "recipe must record cassettes (AC-10)"
    assert "uses_anthropic_cassette" in body, "recipe must select the marker (AC-7)"
    assert "codegenie cassette rebuild-lockfile" in body, "must rebuild lock (AC-11)"


def test_refresh_targets_are_phony() -> None:
    """AC-7 + tests/unit/test_makefile_targets.py contract: every target is .PHONY."""
    text = (REPO_ROOT / "Makefile").read_text()
    phony_decls = re.findall(r"^\.PHONY:\s*(.+)$", text, flags=re.MULTILINE)
    phony_names = {name for line in phony_decls for name in line.split()}
    assert "refresh-cassettes" in phony_names, "refresh-cassettes must be .PHONY"
    assert "_refresh-cassettes-gate" in phony_names, "_refresh-cassettes-gate must be .PHONY"


# ---- CODEOWNERS: well-formed, no placeholder (AC-1, AC-16) -----------------


def test_codeowners_amended_with_well_formed_cassette_rules() -> None:
    """Mutation guard: a literal `@<github-handle>` placeholder (invalid GitHub
    syntax) would ship green against a substring-only check."""
    co = REPO_ROOT / ".github" / "CODEOWNERS"
    assert co.exists(), "CODEOWNERS must already exist — this story amends it"
    text = co.read_text()
    assert "<" not in text and ">" not in text, (
        "CODEOWNERS contains '<' or '>' — likely an unfilled @<…> placeholder"
    )
    rules: dict[str, tuple[str, ...]] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        assert len(parts) >= 2, f"CODEOWNERS line lacks an owner: {line!r}"
        for owner in parts[1:]:
            assert OWNER_RE.fullmatch(owner), f"bad owner token: {owner!r}"
        rules[parts[0]] = tuple(parts[1:])
    for path in (
        "tests/cassettes/anthropic/",
        "tests/cassettes/anthropic/cassettes.lock",
        "docs/operations/cassettes.md",
    ):
        assert path in rules, f"CODEOWNERS missing cassette rule for {path!r}"


# ---- runbook: all 9 sections, heading-shaped (AC-5) ------------------------


def test_cassettes_runbook_has_all_required_section_headings() -> None:
    """Mutation guard: substring-only checks could pass on any prose paragraph
    containing the trigger phrase. Asserting on heading-shaped lines pins the
    structural contract."""
    runbook = REPO_ROOT / "docs" / "operations" / "cassettes.md"
    assert runbook.exists(), "docs/operations/cassettes.md must exist"
    headings = {
        ln.lstrip("#").strip().lower()
        for ln in runbook.read_text().splitlines()
        if ln.lstrip().startswith("#")
    }
    for required in (
        "what cassettes are",
        "four discipline layers",
        "refresh triggers",
        "how to record a new cassette",
        "cassettes.lock format",
        "sanitizer behaviour",
        "codeowners gate",
        "nightly drift job",
        "troubleshooting",
    ):
        assert any(required in h for h in headings), (
            f"runbook missing heading containing {required!r}; headings present: {headings}"
        )


# ---- marker: registered AND attached (AC-8, AC-21) -------------------------


def test_uses_anthropic_cassette_marker_registered() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    markers = pyproject["tool"]["pytest"]["ini_options"]["markers"]
    assert any(m.startswith("uses_anthropic_cassette") for m in markers), (
        f"uses_anthropic_cassette marker must be registered (AC-8); markers={markers}"
    )


def test_uses_anthropic_cassette_marker_is_attached_to_a_test() -> None:
    """Guards the silent no-op: refresh records nothing if no test carries the
    marker. pytest exits 5 ('no tests collected') when -m matches nothing and 0
    when >= 1 is collected — so returncode is the assertion."""
    # Use sys.executable (NOT bare `python`) so the test runs under the same
    # interpreter the harness invoked pytest with — bare `python` is absent on
    # default macOS PATH and would surface as FileNotFoundError instead of the
    # AC-21 silent-no-op diagnostic.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "uses_anthropic_cassette",
            "--collect-only",
            "-q",
            "--no-cov",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "no test carries @pytest.mark.uses_anthropic_cassette — `make refresh-cassettes` "
        f"would be a silent no-op (AC-21); collect output:\n{result.stdout}\n{result.stderr}"
    )


# ---- cross-link surfaces (AC-12, AC-13) ------------------------------------


def test_claude_md_points_at_cassette_runbook() -> None:
    claude = (REPO_ROOT / "CLAUDE.md").read_text()
    assert "docs/operations/cassettes.md" in claude, (
        "CLAUDE.md must reference docs/operations/cassettes.md "
        "as the cassette source-of-truth (AC-12)"
    )


def test_contributing_warns_off_direct_record_mode_invocation() -> None:
    contrib = (REPO_ROOT / "docs" / "contributing.md").read_text()
    assert "make refresh-cassettes" in contrib, (
        "docs/contributing.md must point operators at `make refresh-cassettes` (AC-13)"
    )
    assert "I_UNDERSTAND_THIS_SPENDS_TOKENS=1" in contrib, (
        "docs/contributing.md must surface the explicit-ack make variable (AC-13)"
    )
