"""S5-04 — `LockfilePolicy` YAML loader + `evaluate` (Gap 2 fix).

Covers the smart-constructor boundary (`from_yaml` — every `PolicyLoadError`
variant), the pure evaluator (`evaluate` — host matching, skip paths, sort
determinism), the property/metamorphic invariants, the `PolicyViolation`
discriminator round-trip, and the adversarial malicious-`.npmrc` regression.
"""

from __future__ import annotations

import json
import textwrap
from collections.abc import Mapping
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter, ValidationError

from codegenie.transforms.policy.lockfile_policy import (
    LOCKFILE_POLICY_PATH,
    LockfilePolicy,
    PolicyViolation,
    UnauthorizedRegistry,
)
from codegenie.types.identifiers import RegistryUrl


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "policy.yaml"
    p.write_text(textwrap.dedent(body).lstrip())
    return p


# ---- from_yaml --------------------------------------------------------------


def test_from_yaml_happy_path(tmp_path: Path) -> None:
    p = _write_yaml(
        tmp_path,
        """\
        schema_version: 1
        allowed_registries:
          - https://registry.npmjs.org/
        """,
    )
    result = LockfilePolicy.from_yaml(p)
    assert result.is_ok()
    policy = result.unwrap()
    assert policy.allowed_registries == (RegistryUrl("https://registry.npmjs.org/"),)


def test_from_yaml_file_missing(tmp_path: Path) -> None:
    result = LockfilePolicy.from_yaml(tmp_path / "nope.yaml")
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "file_missing"
    assert err.path == tmp_path / "nope.yaml"


def test_from_yaml_directory_rejected_as_file_missing(tmp_path: Path) -> None:
    # AC-Load-1: is_file() rejects directories — a dir is not a policy file.
    result = LockfilePolicy.from_yaml(tmp_path)
    assert result.is_err()
    assert result.unwrap_err().reason == "file_missing"


def test_from_yaml_yaml_syntax_error(tmp_path: Path) -> None:
    p = tmp_path / "p.yaml"
    p.write_text("foo: [unterminated")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "yaml_syntax"
    assert err.line >= 0 and err.col >= 0
    assert err.detail


def test_from_yaml_unknown_schema_version_2_pins_supported_tuple(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 2\nallowed_registries: [https://x/]\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "unknown_schema_version"
    # AC-Ver-1: a stub that only sets `reason` would fail these two.
    assert err.observed == 2
    assert err.supported == (1,)


def test_from_yaml_empty_allowlist_rejected(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: []\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "empty_allowlist"


def test_from_yaml_invalid_registry_url_http_rejected(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: [http://insecure/]\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "invalid_registry_url"
    assert err.url == "http://insecure/"


def test_from_yaml_invalid_registry_url_no_trailing_slash(tmp_path: Path) -> None:
    p = _write_yaml(
        tmp_path, "schema_version: 1\nallowed_registries: [https://registry.npmjs.org]\n"
    )
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "invalid_registry_url"


def test_from_yaml_extra_field_rejected(tmp_path: Path) -> None:
    p = _write_yaml(
        tmp_path,
        """\
        schema_version: 1
        allowed_registries: [https://registry.npmjs.org/]
        sneaky_extra_field: true
        """,
    )
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "schema_violation"


def test_from_yaml_null_allowed_registries_rejected(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, "schema_version: 1\nallowed_registries: null\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "schema_violation"


def test_from_yaml_non_mapping_document_rejected(tmp_path: Path) -> None:
    # A YAML that loads to a list (not a mapping) has no `schema_version` to
    # early-exit on — it must fall through to Pydantic and be a schema_violation.
    p = _write_yaml(tmp_path, "- just\n- a\n- list\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "schema_violation"


def test_from_yaml_first_failing_step_wins(tmp_path: Path) -> None:
    # AC-Load-2: schema_version is checked BEFORE schema-validation /
    # empty-allowlist / per-URL — the first failing step wins.
    p = _write_yaml(tmp_path, "schema_version: 2\nallowed_registries: []\nsneaky: true\n")
    result = LockfilePolicy.from_yaml(p)
    assert result.is_err()
    assert result.unwrap_err().reason == "unknown_schema_version"


# ---- evaluate ---------------------------------------------------------------


@pytest.fixture
def npm_policy() -> LockfilePolicy:
    return LockfilePolicy(
        schema_version=1,
        allowed_registries=(RegistryUrl("https://registry.npmjs.org/"),),
    )


def test_evaluate_empty_packages_returns_no_violations(npm_policy: LockfilePolicy) -> None:
    assert npm_policy.evaluate({"packages": {}}) == []


def test_evaluate_missing_packages_key_returns_no_violations(
    npm_policy: LockfilePolicy,
) -> None:
    assert npm_policy.evaluate({"lockfileVersion": 3}) == []


def test_evaluate_packages_not_a_mapping_returns_no_violations(
    npm_policy: LockfilePolicy,
) -> None:
    # Defensive: a corrupted lockfile shape must not crash — just yield nothing.
    assert npm_policy.evaluate({"packages": [1, 2, 3]}) == []


def test_evaluate_root_pkg_without_resolved_is_skipped(npm_policy: LockfilePolicy) -> None:
    doc: Mapping[str, object] = {"packages": {"": {"name": "root", "version": "1.0.0"}}}
    assert npm_policy.evaluate(doc) == []


def test_evaluate_link_workspace_dep_skipped(npm_policy: LockfilePolicy) -> None:
    doc: Mapping[str, object] = {
        "packages": {"node_modules/local-pkg": {"link": True, "resolved": None}}
    }
    assert npm_policy.evaluate(doc) == []


def test_evaluate_entry_not_a_mapping_is_skipped(npm_policy: LockfilePolicy) -> None:
    doc: Mapping[str, object] = {"packages": {"node_modules/weird": "not-a-dict"}}
    assert npm_policy.evaluate(doc) == []


def test_evaluate_legit_registry_passes(npm_policy: LockfilePolicy) -> None:
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "version": "4.19.2",
                "resolved": "https://registry.npmjs.org/express/-/express-4.19.2.tgz",
            }
        }
    }
    assert npm_policy.evaluate(doc) == []


def test_evaluate_attacker_host_yields_violation(npm_policy: LockfilePolicy) -> None:
    # The Gap 2 regression — an attacker host on a `resolved` URL.
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "version": "4.19.2",
                "resolved": "https://attacker.example.com/express/-/express-4.19.2.tgz",
            }
        }
    }
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, UnauthorizedRegistry)
    assert v.registry == RegistryUrl("https://attacker.example.com/")
    assert v.package == "node_modules/express"


def test_evaluate_port_mismatch_is_violation(npm_policy: LockfilePolicy) -> None:
    # AC-Eval-4 strict netloc equality — :443 != no-port even for default https.
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "resolved": "https://registry.npmjs.org:443/express/-/express-4.19.2.tgz",
            }
        }
    }
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1
    assert violations[0].registry == RegistryUrl("https://registry.npmjs.org:443/")


def test_evaluate_userinfo_in_url_is_violation(npm_policy: LockfilePolicy) -> None:
    # AC-Eval-4 credentials in the URL make the netloc differ → host mismatch.
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "resolved": "https://user:pass@registry.npmjs.org/express/-/express-4.19.2.tgz",
            }
        }
    }
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1


def test_evaluate_http_scheme_is_violation(npm_policy: LockfilePolicy) -> None:
    # AC-Eval-4 strict scheme — http:// != https:// for the same host.
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/express": {
                "resolved": "http://registry.npmjs.org/express/-/express-4.19.2.tgz",
            }
        }
    }
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1


def test_evaluate_violations_sorted_deterministically(npm_policy: LockfilePolicy) -> None:
    # AC-Eval-6 stable sort by (package, registry) — golden-file determinism.
    doc: Mapping[str, object] = {
        "packages": {
            "node_modules/z-bad": {"resolved": "https://evil2.example/z/-/z-1.tgz"},
            "node_modules/a-bad": {"resolved": "https://evil1.example/a/-/a-1.tgz"},
            "node_modules/m-bad": {"resolved": "https://evil1.example/m/-/m-1.tgz"},
        }
    }
    violations = npm_policy.evaluate(doc)
    assert [v.package for v in violations] == [
        "node_modules/a-bad",
        "node_modules/m-bad",
        "node_modules/z-bad",
    ]


# ---- property-based / metamorphic (AC-Adv-2, AC-Adv-3) ----------------------

_HOST = st.from_regex(r"^[a-z][a-z0-9.-]{2,40}$", fullmatch=True)


@settings(max_examples=200, deadline=None)
@given(
    allowed_hosts=st.lists(_HOST, min_size=1, max_size=4, unique=True),
    pkg_host=_HOST,
)
def test_property_evaluate_iff_host_not_in_allowlist(
    allowed_hosts: list[str], pkg_host: str
) -> None:
    allowed = tuple(RegistryUrl(f"https://{h}/") for h in allowed_hosts)
    policy = LockfilePolicy(schema_version=1, allowed_registries=allowed)
    doc: Mapping[str, object] = {
        "packages": {"node_modules/p": {"resolved": f"https://{pkg_host}/p/-/p-1.tgz"}}
    }
    violations = policy.evaluate(doc)
    in_allowlist = any(pkg_host == h for h in allowed_hosts)
    assert (len(violations) == 0) == in_allowlist


@settings(max_examples=100, deadline=None)
@given(
    base_hosts=st.lists(_HOST, min_size=1, max_size=3, unique=True),
    extra_hosts=st.lists(_HOST, min_size=0, max_size=3, unique=True),
    pkg_hosts=st.lists(_HOST, min_size=1, max_size=5),
)
def test_metamorphic_widening_allowlist_only_reduces_violations(
    base_hosts: list[str], extra_hosts: list[str], pkg_hosts: list[str]
) -> None:
    # AC-Adv-3: adding to allowed_registries can only reduce or preserve count.
    p_strict = LockfilePolicy(
        schema_version=1,
        allowed_registries=tuple(RegistryUrl(f"https://{h}/") for h in base_hosts),
    )
    p_loose = LockfilePolicy(
        schema_version=1,
        allowed_registries=tuple(RegistryUrl(f"https://{h}/") for h in {*base_hosts, *extra_hosts}),
    )
    doc: Mapping[str, object] = {
        "packages": {
            f"node_modules/p{i}": {"resolved": f"https://{h}/p{i}/-/p{i}-1.tgz"}
            for i, h in enumerate(pkg_hosts)
        }
    }
    assert len(p_loose.evaluate(doc)) <= len(p_strict.evaluate(doc))


# ---- PolicyViolation discriminator (AC-Union-3) -----------------------------


def test_policy_violation_typeadapter_round_trip() -> None:
    adapter = TypeAdapter(PolicyViolation)
    obj = adapter.validate_python(
        {"kind": "unauthorized_registry", "registry": "https://x/", "package": "p"}
    )
    assert isinstance(obj, UnauthorizedRegistry)
    assert adapter.dump_python(obj)["kind"] == "unauthorized_registry"


def test_policy_violation_typeadapter_rejects_unknown_kind() -> None:
    adapter = TypeAdapter(PolicyViolation)
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "not_a_real_kind", "registry": "https://x/", "package": "p"}
        )


# ---- adversarial regression: malicious-npmrc fixture (AC-Adv-1) -------------


def _malicious_npmrc_lockfile() -> Path:
    # Resolved against the test file, not cwd — AC-Adv-1 cwd-independence.
    return (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "repos"
        / "malicious-npmrc"
        / "package-lock.json"
    )


def test_attacker_npmrc_lockfile_yields_unauthorized_registry(
    npm_policy: LockfilePolicy,
) -> None:
    doc = json.loads(_malicious_npmrc_lockfile().read_text(encoding="utf-8"))
    violations = npm_policy.evaluate(doc)
    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, UnauthorizedRegistry)
    assert v.registry == RegistryUrl("https://attacker.example.com/")
    assert v.package == "node_modules/express"


def test_attacker_npmrc_check_is_cwd_independent(
    npm_policy: LockfilePolicy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = json.loads(_malicious_npmrc_lockfile().read_text(encoding="utf-8"))
    monkeypatch.chdir(tmp_path)
    assert len(npm_policy.evaluate(doc)) == 1


# ---- shipped policy parses --------------------------------------------------


def test_shipped_lockfile_policy_yaml_loads_clean() -> None:
    result = LockfilePolicy.from_yaml(LOCKFILE_POLICY_PATH)
    assert result.is_ok()
    policy = result.unwrap()
    assert RegistryUrl("https://registry.npmjs.org/") in policy.allowed_registries
