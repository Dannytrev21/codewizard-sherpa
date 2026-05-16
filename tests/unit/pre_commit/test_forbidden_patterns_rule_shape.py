"""S1-11 — structural ``Rule`` dataclass / Open-Closed (AC-15).

Adding a future path-scoped rule (e.g., a Phase-3 ban of ``httpx`` under
``src/codegenie/plugins/``) must require only one new ``Rule(...)`` entry —
zero edits to ``_scan_file()`` or ``main()``. The structural test pins this.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-11-forbidden-patterns-mypy-adrs.md``
  §AC-15.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_forbidden_patterns.py"
_MOD_NAME = "_check_forbidden_patterns_for_test"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MOD_NAME, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec — dataclass(slots=True) under
    # `from __future__ import annotations` resolves string annotations via
    # `sys.modules[cls.__module__]`; without this, slot synthesis raises.
    sys.modules[_MOD_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


def test_every_rule_row_has_applies_when_callable() -> None:
    """AC-15 — every ``_RULES`` row must expose an ``applies_when`` callable."""
    mod = _load_script_module()
    rules = mod._RULES
    assert len(rules) >= 12, (
        f"expected at least 12 rules (11 Phase-0 + 1 Phase-2); got {len(rules)}"
    )
    for rule in rules:
        assert callable(rule.applies_when), f"rule {rule.label!r} lacks callable applies_when"


def test_model_construct_rule_path_scoping() -> None:
    """AC-15 — the model_construct rule's ``applies_when`` is the SINGLE source
    of truth for path scoping. Pinned on representative paths.
    """
    mod = _load_script_module()
    rule = next(r for r in mod._RULES if "model_construct" in r.label)
    assert rule.applies_when(Path("src/codegenie/indices/freshness.py")) is True
    assert rule.applies_when(Path("src/codegenie/tccm/loader.py")) is True
    assert rule.applies_when(Path("src/codegenie/output/sanitizer.py")) is True
    assert rule.applies_when(Path("src/codegenie/probes/layer_a/foo.py")) is False
    assert rule.applies_when(Path("src/codegenie/cli.py")) is False
    assert rule.applies_when(Path("tests/unit/test_foo.py")) is False


def test_phase0_rules_use_default_always_predicate() -> None:
    """AC-15 — the 11 Phase-0 rules must remain repo-wide (default predicate
    returns True for any path), not silently scoped by the refactor.
    """
    mod = _load_script_module()
    arbitrary = Path("src/codegenie/anywhere/foo.py")
    phase0_labels = {
        "print(",
        "yaml.load( without Loader=",
        "shell=True",
        "subprocess.run(..., shell=...)",
        "yaml.Dumper",
        "os.system(",
        "os.popen(",
        "pickle.loads(",
        "eval(",
        "exec(",
        "__import__(",
    }
    for rule in mod._RULES:
        if rule.label in phase0_labels:
            assert rule.applies_when(arbitrary) is True, (
                f"Phase-0 rule {rule.label!r} silently scoped — must remain repo-wide"
            )
