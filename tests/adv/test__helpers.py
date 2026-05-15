"""Unit tests for the adversarial-fixture pure builders (S5-01 AC-16).

Each pure builder defined in a sibling ``test_*.py`` module is exercised
here for deterministic byte-output (same input → same bytes) — the
contract that lets the imperative-shell writers stream them to disk
without surprises.

Also covers the ``expected_lockfile_error_id`` drift-guard helper —
fixing the prefix to ``pnpm_lock`` / ``yarn_lock`` / ``npm_lock`` and
the four exception suffixes against the registry constants.
"""

from __future__ import annotations

from codegenie.errors import (
    DepthCapExceeded,
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from tests.adv._helpers import expected_lockfile_error_id


def test_billion_laughs_yaml_is_deterministic() -> None:
    from tests.adv.test_yaml_billion_laughs import _billion_laughs_yaml

    a = _billion_laughs_yaml(depth=8)
    b = _billion_laughs_yaml(depth=8)
    assert a == b
    assert isinstance(a, bytes)
    # depth controls nesting — bigger depth → bigger byte output.
    assert len(_billion_laughs_yaml(depth=16)) > len(a)


def test_deeply_nested_package_json_is_deterministic() -> None:
    from tests.adv.test_json_bomb_deep_nesting import _deeply_nested_package_json

    a = _deeply_nested_package_json(depth=4)
    b = _deeply_nested_package_json(depth=4)
    assert a == b
    assert isinstance(a, bytes)
    assert len(_deeply_nested_package_json(depth=16)) > len(a)


def test_expected_lockfile_error_id_constructs_from_registry() -> None:
    # The drift guard — the four ID flavours every adversarial cap-family
    # test pins on the slice ``errors`` field.
    assert expected_lockfile_error_id("pnpm", DepthCapExceeded) == "pnpm_lock.depth_cap_exceeded"
    assert expected_lockfile_error_id("pnpm", SizeCapExceeded) == "pnpm_lock.size_cap_exceeded"
    assert expected_lockfile_error_id("yarn", MalformedLockfileError) == "yarn_lock.malformed"
    assert expected_lockfile_error_id("npm", SymlinkRefusedError) == "npm_lock.symlink_refused"
