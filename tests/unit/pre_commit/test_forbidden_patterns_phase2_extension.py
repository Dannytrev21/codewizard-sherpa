"""S1-11 — Phase-2 ``model_construct`` ban surface (AC-1, AC-2, AC-3, AC-14).

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-11-forbidden-patterns-mypy-adrs.md``
  §"Acceptance criteria" AC-1..AC-3, AC-14.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/`` ->
  ``0010-redacted-slice-smart-constructor-at-writer-boundary.md`` §Decision —
  the smart-constructor invariant the ban defends.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §3 — typed
  identifiers / smart-constructor discipline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BANNED_PACKAGES = (
    "indices",
    "tccm",
    "skills",
    "conventions",
    "adapters",
    "depgraph",
    "output",
)
ALLOWED_PHASE0_PATHS = ("probes/layer_a",)

# Mutation-resistance forms — a regex that only catches one of these would
# silently pass weaker tests. Each form is a syntactic variant a contributor
# could plausibly write.
SOURCE_FORMS = {
    "class_call": "class Foo:\n    pass\nFoo.model_construct(x=1)\n",
    "instance_call": "class Foo:\n    pass\nfoo = Foo()\nfoo.model_construct(x=1)\n",
    "renamed_class": "class MyVerySpecificName:\n    pass\nMyVerySpecificName.model_construct()\n",
    "kwarg": "def bar(model_construct=None):\n    pass\n",
}

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_forbidden_patterns.py"


def _write_synth(tmp_path: Path, rel: str, body: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


@pytest.mark.parametrize("pkg", BANNED_PACKAGES)
@pytest.mark.parametrize("form_name,body", list(SOURCE_FORMS.items()))
def test_model_construct_banned_under_phase2_packages(
    tmp_path: Path, pkg: str, form_name: str, body: str
) -> None:
    """AC-1, AC-2 — every banned package x every source form must trip the hook.

    The 28-cell matrix (7 packages x 4 forms) is the mutation guard:
    weakening the regex collapses one column instead of one cell.
    """
    target = _write_synth(tmp_path, f"src/codegenie/{pkg}/synth_{form_name}.py", body)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"hook must reject model_construct under {pkg} ({form_name}); "
        f"got exit 0; output:\n{combined}"
    )
    assert "02-ADR-0010 §Decision" in combined, f"missing 02-ADR-0010 §Decision in: {combined}"
    assert "production ADR-0033 §3" in combined, f"missing production ADR-0033 §3 in: {combined}"


@pytest.mark.parametrize("pkg", ALLOWED_PHASE0_PATHS)
def test_model_construct_not_banned_under_phase0_phase1_packages(tmp_path: Path, pkg: str) -> None:
    """AC-3 — surgical rollout discipline; the ``applies_when`` predicate is honored."""
    body = SOURCE_FORMS["class_call"]
    target = _write_synth(tmp_path, f"src/codegenie/{pkg}/synth.py", body)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"hook must NOT reject model_construct under {pkg} (Phase 0/1); "
        f"got exit {result.returncode}; output:\n{result.stdout}{result.stderr}"
    )


def test_existing_phase0_rules_still_fire(tmp_path: Path) -> None:
    """AC-14 — regression guard: refactoring ``_RULES`` row shape must not
    silently drop any of the 11 Phase-0 rules. Each banned construct in turn
    must produce a non-zero exit + the expected rule label.
    """
    cases = {
        "print(": "print('hello')\n",
        "yaml.load( without Loader=": "import yaml\nyaml.load('x:y')\n",
        "shell=True": "import subprocess\nsubprocess.run('ls', shell=True)\n",
        "yaml.Dumper": "import yaml\nyaml.dump({}, Dumper=yaml.Dumper)\n",
        "os.system(": "import os\nos.system('ls')\n",
        "os.popen(": "import os\nos.popen('ls')\n",
        "pickle.loads(": "import pickle\npickle.loads(b'')\n",
        "eval(": "eval('1+1')\n",
        "exec(": "exec('pass')\n",
        "__import__(": "__import__('os')\n",
    }
    for label, body in cases.items():
        # Place under a Phase-1 path so the model_construct rule does NOT also
        # fire (would muddy attribution); only Phase-0 (default-always) rules
        # apply here.
        target = _write_synth(tmp_path, f"src/codegenie/probes/layer_a/synth_{label[:6]}.py", body)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        combined = result.stdout + result.stderr
        assert result.returncode != 0, (
            f"Phase-0 rule `{label}` no longer fires; output:\n{combined}"
        )
        assert label in combined, (
            f"Phase-0 rule `{label}` fired but its label is missing from output:\n{combined}"
        )
