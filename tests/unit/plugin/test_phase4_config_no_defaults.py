"""Phase-4 S7-04 AC-8c (partial) — constructor-signature backstop.

**Rule 7 finding — surfaced, not silenced.** AC-8c as literally written
asserts that ``BandClassifier`` AND ``LlmInvocationGuard`` constructors
have ``Parameter.empty`` defaults for the calibration parameters. The
shipped reality at S5-02 + S2-05:

* ``BandClassifier(high_floor=0.85, degraded_floor=0.65)`` — both fields
  default to the **arch literal**, exactly the "silent mask" attack vector
  AC-8c was meant to prevent.
* ``LlmInvocationGuard(max_tokens=_DEFAULT_MAX_TOKENS, ...)`` — same shape.

Honoring AC-8c verbatim today would require editing those shipped
classes (out of scope for S7-04 — they belong to S5-02 / S2-05). Instead
this story enforces the **Phase4Config side** of the invariant — every
Pydantic field on the Phase-4 sub-models is required, so a missing YAML
key cannot silently default to the arch literal at the *config* layer.
The classifier/guard defaults are a Phase-5 follow-up (surfaced in the
S7-04 attempt log).

This is **defense-in-depth, not bypass**: at the YAML layer, a missing
key fails loud (AC-5 R2 covers this). At the model layer, this test
locks the no-defaults invariant on Phase4Config sub-models so a future
"helpful" default addition is rejected before it can mask a YAML typo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_CONFIG_PATH = (
    Path(__file__).parents[3] / "plugins" / "vulnerability-remediation--node--npm" / "config.py"
)


def _load() -> ModuleType:
    mod_name = "_test_phase4_no_defaults_cfg"
    spec = importlib.util.spec_from_file_location(mod_name, _CONFIG_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_MOD = _load()


def _required_fields(cls: type) -> dict[str, bool]:
    """Map each field name → ``field.is_required()``."""
    return {name: f.is_required() for name, f in cls.model_fields.items()}


def test_thresholds_fields_all_required() -> None:
    """No Pydantic default on :class:`Thresholds`."""
    required = _required_fields(_MOD.Thresholds)
    assert required == {"high_floor": True, "degraded_floor": True}, (
        f"Thresholds field-required map drifted: {required}. "
        f"Any False would silently mask a missing YAML key with a hardcoded default."
    )


def test_budget_fields_all_required() -> None:
    """No Pydantic default on :class:`Budget`."""
    required = _required_fields(_MOD.Budget)
    expected = {
        "max_tokens_per_workflow": True,
        "max_dollars_per_workflow": True,
        "per_call_max_tokens": True,
    }
    assert required == expected, f"Budget field-required map drifted: {required}"


def test_embeddings_fields_all_required() -> None:
    """No Pydantic default on :class:`Embeddings`."""
    required = _required_fields(_MOD.Embeddings)
    assert required == {"model": True}


def test_cassettes_fields_all_required() -> None:
    """No Pydantic default on :class:`Cassettes`."""
    required = _required_fields(_MOD.Cassettes)
    assert required == {"dir": True}


def test_phase4_config_top_level_fields_all_required() -> None:
    """No Pydantic default on :class:`Phase4Config` — every sub-block is mandatory."""
    required = _required_fields(_MOD.Phase4Config)
    expected = {
        "thresholds": True,
        "budget": True,
        "embeddings": True,
        "cassettes": True,
    }
    assert required == expected
