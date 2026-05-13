"""``OutputSanitizer.scrub`` — two-pass chokepoint (ADR-0008, ADR-0010).

Pins ACs 1-13, 24-25 from story S3-03: ``SanitizedProbeOutput`` shape,
defense-in-depth secret rejection at depth, path-scrub (embedded, outside-repo,
re.escape, symlink-root, longest-prefix-wins), repo_root precondition, no-leak
global invariant, determinism+idempotence, empty-input round-trip, and
structlog event pinning.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
from dataclasses import asdict
from pathlib import Path

import pytest
import structlog.testing

from codegenie.coordinator.validator import SECRET_FIELD_PATTERN as CANONICAL
from codegenie.errors import SecretLikelyFieldNameError
from codegenie.output import sanitizer as san
from codegenie.output.sanitizer import OutputSanitizer, SanitizedProbeOutput
from codegenie.probes.base import ProbeOutput


def _probe(
    *,
    schema_slice: dict[str, object] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> ProbeOutput:
    return ProbeOutput(
        schema_slice=schema_slice if schema_slice is not None else {},
        raw_artifacts=[],
        confidence="high",
        duration_ms=1,
        warnings=warnings or [],
        errors=errors or [],
    )


def _iter_strings(node: object) -> list[str]:
    out: list[str] = []

    def walk(x: object) -> None:
        if isinstance(x, str):
            out.append(x)
            return
        if isinstance(x, dict):
            for k, v in x.items():
                walk(k)
                walk(v)
            return
        if isinstance(x, list):
            for v in x:
                walk(v)
            return

    walk(node)
    return out


def _resolved_tmp(tmp_path: Path) -> Path:
    return tmp_path.resolve()


# AC-1 / AC-2 — SanitizedProbeOutput field-set parity, frozen
def test_sanitized_probe_output_field_parity() -> None:
    assert {f.name for f in dataclasses.fields(SanitizedProbeOutput)} == {
        f.name for f in dataclasses.fields(ProbeOutput)
    }


def test_sanitized_probe_output_is_frozen() -> None:
    s = SanitizedProbeOutput(
        schema_slice={},
        raw_artifacts=[],
        confidence="high",
        duration_ms=0,
        warnings=[],
        errors=[],
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.confidence = "low"  # type: ignore[misc]


# AC-3 — secret pattern is imported by identity, no inline re.compile
def test_sanitizer_uses_canonical_secret_pattern_by_identity() -> None:
    assert san.SECRET_FIELD_PATTERN is CANONICAL


def test_sanitizer_module_does_not_redefine_secret_regex() -> None:
    tree = ast.parse(inspect.getsource(san))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re"
        ):
            # A per-call ``re.compile`` for the path regex (inside ``scrub``)
            # is permitted; only secret-regex re-definition is banned. Tag the
            # secret regex by the presence of ``secret`` in its source text.
            src = ast.unparse(node)
            if "secret" in src.lower() or "token" in src.lower():
                pytest.fail(
                    f"sanitizer.py compiles a secret-named regex at line {node.lineno}; "
                    "must import SECRET_FIELD_PATTERN from coordinator.validator"
                )


# AC-4 — depth-N secret-key rejection (parametrized)
SECRET_KEYS = [
    "github_token",
    "api_key",
    "AWS_SECRET_ACCESS_KEY",
    "client_secret",
    "Bearer-Token",
    "PRIVATE_KEY",
]


def _nest(key: str, depth: int) -> dict[str, object]:
    node: object = {key: "<value>"}
    for i in range(depth - 1):
        node = {"layer": node} if i % 2 == 0 else [node]
    # Ensure the outer return is a dict (schema_slice is dict-typed).
    return {"root": node} if not isinstance(node, dict) else node


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("key", SECRET_KEYS)
def test_pass1_rejects_secret_key_at_any_depth(tmp_path: Path, depth: int, key: str) -> None:
    out = _probe(schema_slice=_nest(key, depth))
    with pytest.raises(SecretLikelyFieldNameError) as exc:
        OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))
    assert exc.value.args[0] == key


BENIGN_KEYS = [
    "description",
    "language",
    # Note: anything containing 'token' (e.g. 'tokens_per_line') correctly
    # trips the canonical SECRET_FIELD_PATTERN — the regex prefers false
    # positives over silent leaks (ADR-0010 §Tradeoffs). Benign matrix is
    # restricted to names with no substring overlap.
    "package_name",
    "test_count",
    "exit_status",
]


@pytest.mark.parametrize("key", BENIGN_KEYS)
def test_pass1_does_not_reject_benign_keys(tmp_path: Path, key: str) -> None:
    out = _probe(schema_slice={key: "value"})
    OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))


# AC-5 — embedded mid-string path scrub
def test_pass2_scrubs_embedded_path_in_error_string(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    msg = f"FileNotFoundError: /Users/danny/foo.js while reading {tmp}/src/a.js"
    out = _probe(errors=[msg])
    result = OutputSanitizer().scrub(out, repo_root=tmp)
    assert "/Users/danny/" not in result.errors[0]
    assert str(tmp) not in result.errors[0]


# AC-6 — pass-2 walks schema_slice, errors, warnings
def test_pass2_scrubs_errors_field(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    out = _probe(errors=[f"error at {tmp}/src/x.js", "/Users/bob/other"])
    result = OutputSanitizer().scrub(out, repo_root=tmp)
    for s in result.errors:
        assert not s.startswith("/Users/")
        assert str(tmp) not in s


def test_pass2_scrubs_warnings_field(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    out = _probe(warnings=["deprecated: /home/alice/lib"])
    result = OutputSanitizer().scrub(out, repo_root=tmp)
    assert "/home/alice/" not in result.warnings[0]


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_pass2_walks_arbitrary_depth(tmp_path: Path, depth: int) -> None:
    tmp = _resolved_tmp(tmp_path)
    leaf = str(tmp / "src" / "a.js")
    node: object = leaf
    for i in range(depth):
        node = {"l": node} if i % 2 == 0 else [node]
    out = _probe(schema_slice={"root": node})
    result = OutputSanitizer().scrub(out, repo_root=tmp).schema_slice
    flat = _iter_strings(result)
    # The original leaf string was rewritten to "src/a.js" — and no string
    # in the result contains the original absolute prefix.
    assert "src/a.js" in flat
    assert f"{tmp}/src/a.js" not in flat
    assert all(str(tmp) not in s for s in flat)


# AC-7 — re.escape applied
def test_pass2_escapes_regex_metachars_in_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo.git"
    repo.mkdir()
    repo = repo.resolve()
    decoy = tmp_path.resolve() / "repoXgit" / "foo"
    out = _probe(
        schema_slice={
            "real": f"{repo}/src/a.js",
            "decoy": str(decoy),
        }
    )
    result = OutputSanitizer().scrub(out, repo_root=repo).schema_slice
    assert result["real"] == "src/a.js"
    assert result["decoy"] == str(decoy)


# AC-8 — symlinked repo_root resolves to real
def test_pass2_resolves_symlinked_repo_root(tmp_path: Path) -> None:
    real = tmp_path / "real_repo"
    real.mkdir()
    real = real.resolve()
    link = tmp_path / "link"
    link.symlink_to(real)
    link_resolved = link.resolve()
    out = _probe(schema_slice={"file": str(real / "src" / "a.js")})
    result = OutputSanitizer().scrub(out, repo_root=link_resolved).schema_slice["file"]
    assert result == "src/a.js"


# AC-9 — under-repo → relative; outside repo under /Users/<u>/ → strip user segment
def test_pass2_under_repo_is_relative(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": f"{tmp}/src/a.js"})
    assert OutputSanitizer().scrub(out, repo_root=tmp).schema_slice["f"] == "src/a.js"


def test_pass2_outside_repo_under_users_strips_user_segment(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": "/Users/danny/other-repo/x.js"})
    result = OutputSanitizer().scrub(out, repo_root=tmp).schema_slice["f"]
    assert result == "other-repo/x.js"
    assert "danny" not in result


def test_pass2_outside_repo_under_root_strips_root(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": "/root/work/x.js"})
    result = OutputSanitizer().scrub(out, repo_root=tmp).schema_slice["f"]
    assert result == "work/x.js"


# AC-10 — longest-prefix-wins
def test_pass2_repo_under_users_prefers_repo_prefix(tmp_path: Path) -> None:
    fake_home = tmp_path / "Users" / "danny" / "repo"
    fake_home.mkdir(parents=True)
    repo = fake_home.resolve()
    out = _probe(schema_slice={"f": f"{repo}/src/a.js"})
    result = OutputSanitizer().scrub(out, repo_root=repo).schema_slice["f"]
    assert result == "src/a.js"


# AC-11 — repo_root precondition
def test_scrub_rejects_relative_repo_root() -> None:
    with pytest.raises(ValueError):
        OutputSanitizer().scrub(_probe(), repo_root=Path("repo"))


def test_scrub_rejects_unresolved_repo_root(tmp_path: Path) -> None:
    nested = tmp_path / "a" / ".." / "a"
    (tmp_path / "a").mkdir()
    with pytest.raises(ValueError):
        OutputSanitizer().scrub(_probe(), repo_root=nested)


def test_scrub_rejects_root_slash() -> None:
    with pytest.raises(ValueError):
        OutputSanitizer().scrub(_probe(), repo_root=Path("/"))


# AC-12 — no-leak global invariant
FORBIDDEN_PREFIXES = ("/Users/", "/home/", "/root/")


def test_no_path_leaks_anywhere_after_scrub(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    messy: dict[str, object] = {
        "f1": "/Users/danny/x",
        "f2": "/home/alice/y",
        "f3": "/root/z",
        "f4": f"{tmp}/a.js",
        "nested": {
            "list": ["/Users/bob/c", f"{tmp}/b", "ok-relative"],
            "deeper": {"x": "/home/charlie/d.js"},
        },
    }
    out = _probe(
        schema_slice=messy,
        errors=[f"err at {tmp}/c.js"],
        warnings=["/Users/dave/w.js"],
    )
    result = OutputSanitizer().scrub(out, repo_root=tmp)
    for s in _iter_strings(result.schema_slice) + result.errors + result.warnings:
        assert not s.startswith(FORBIDDEN_PREFIXES), f"leak: {s!r}"
        assert str(tmp) not in s, f"repo_root leak: {s!r}"


# AC-13 — determinism + idempotence
def _as_probe_output(s: SanitizedProbeOutput) -> ProbeOutput:
    return ProbeOutput(
        schema_slice=s.schema_slice,
        raw_artifacts=s.raw_artifacts,
        confidence=s.confidence,
        duration_ms=s.duration_ms,
        warnings=s.warnings,
        errors=s.errors,
    )


def test_scrub_is_deterministic_across_instances(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": f"{tmp}/src/a.js", "g": "/Users/x/y"})
    s1 = OutputSanitizer().scrub(out, repo_root=tmp)
    s2 = OutputSanitizer().scrub(out, repo_root=tmp)
    assert json.dumps(asdict(s1), sort_keys=False) == json.dumps(asdict(s2), sort_keys=False)


def test_scrub_is_idempotent_and_does_work(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": f"{tmp}/src/a.js"})
    once = OutputSanitizer().scrub(out, repo_root=tmp)
    assert once.schema_slice["f"] == "src/a.js"
    twice = OutputSanitizer().scrub(_as_probe_output(once), repo_root=tmp)
    assert asdict(twice) == asdict(once)


# AC-25 — structlog event emission pinning
def test_pass1_emits_secret_rejected_event(tmp_path: Path) -> None:
    out = _probe(schema_slice={"github_token": "x"})
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(SecretLikelyFieldNameError):
            OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))
    assert any(r.get("event") == "sanitizer.secret.rejected" for r in captured)


def test_pass2_emits_path_rewritten_at_debug(tmp_path: Path) -> None:
    tmp = _resolved_tmp(tmp_path)
    out = _probe(schema_slice={"f": f"{tmp}/x"})
    with structlog.testing.capture_logs() as captured:
        OutputSanitizer().scrub(out, repo_root=tmp)
    rewrites = [r for r in captured if r.get("event") == "sanitizer.path.rewritten"]
    assert len(rewrites) == 1
    assert rewrites[0]["log_level"] == "debug"


def test_clean_input_emits_no_rewrite_events(tmp_path: Path) -> None:
    out = _probe(schema_slice={"f": "src/already-relative.js"})
    with structlog.testing.capture_logs() as captured:
        OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))
    assert not [r for r in captured if r.get("event") == "sanitizer.path.rewritten"]


# AC-24 — empty input round-trip
def test_scrub_empty_schema_slice_roundtrips(tmp_path: Path) -> None:
    out = _probe()
    result = OutputSanitizer().scrub(out, repo_root=_resolved_tmp(tmp_path))
    assert result.schema_slice == {}
    assert result.errors == []
    assert result.warnings == []
