"""AC-18 — Hypothesis property-based tests.

Three properties:

* DenyAll → no ``--share-net`` / ``--bind-net-*`` / ``--unshare-net=false``.
* Allowlist host coverage → every host in ``spec.network.hosts`` is
  forwarded to ``_setup_netns_with_allowlist`` (set-equality).
* Verbatim cmd preservation → ``cmd`` is the strict tail of the argv.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.exec import ProcessResult
from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.sandbox_jail import DenyAll, NpmEnv, RegistryAllowlist
from codegenie.types.identifiers import RegistryUrl
from tests.unit.transforms.sandbox._fakes import make_spec


def _cmd_token() -> st.SearchStrategy[str]:
    """Non-empty cmd tokens — printable, no NULs."""
    return st.text(
        alphabet=st.characters(
            min_codepoint=0x21, max_codepoint=0x7E, blacklist_characters=("\x00",)
        ),
        min_size=1,
        max_size=12,
    )


@given(cmd=st.lists(_cmd_token(), min_size=1, max_size=5).map(tuple))
@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@pytest.mark.asyncio
async def test_property_cmd_is_strict_tail_of_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cmd: tuple[str, ...]
) -> None:
    captured: dict[str, list[str]] = {}

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        captured["argv"] = list(argv)
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    await BwrapAdapter().run(make_spec(tmp_path, cmd=cmd))
    argv = captured["argv"]
    assert tuple(argv[-len(cmd) :]) == cmd


@given(st.builds(lambda: None))  # 1-shot driver: DenyAll has no parameters
@settings(
    max_examples=5,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@pytest.mark.asyncio
async def test_property_denyall_never_shares_net(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _ignored: None
) -> None:
    captured: dict[str, list[str]] = {}

    async def fake(argv: list[str], **_: Any) -> ProcessResult:
        captured["argv"] = list(argv)
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    await BwrapAdapter().run(make_spec(tmp_path, network=DenyAll()))
    argv = captured["argv"]
    assert "--share-net" not in argv
    assert not any(a.startswith("--bind-net") for a in argv)
    assert "--unshare-net=false" not in argv


_HOST_NAMES = ("registry.npmjs.org", "registry.yarnpkg.com", "registry.example.com")


@given(
    chosen=st.lists(st.sampled_from(_HOST_NAMES), min_size=1, max_size=3, unique=True),
)
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@pytest.mark.asyncio
async def test_property_allowlist_hosts_fully_propagated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chosen: list[str]
) -> None:
    captured_hosts: list[frozenset[str]] = []

    def fake_setup(hosts: frozenset[str]) -> Any:
        captured_hosts.append(hosts)
        return type("H", (), {"name": "ns"})()

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._setup_netns_with_allowlist",
        fake_setup,
    )
    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._teardown_netns",
        lambda h: None,
    )

    async def fake_run(argv: list[str], **_: Any) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake_run)

    urls = frozenset(RegistryUrl(f"https://{h}") for h in chosen)
    await BwrapAdapter().run(
        make_spec(tmp_path, env=NpmEnv(), network=RegistryAllowlist(hosts=urls))
    )
    assert captured_hosts, "_setup_netns_with_allowlist was not invoked"
    assert captured_hosts[0] == {str(u) for u in urls}
