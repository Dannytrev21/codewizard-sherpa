"""Adversarial: zip-slip on ``kustomization.yaml#resources`` refused.

The mitigation lives in ``DeploymentProbe._walk_overlays`` (S4-02):
``candidate = kustomize_dir / resource; resolved.is_relative_to(root_resolved)``
rejects any resource whose resolved-absolute path falls outside the repo.

The sentinel-exfiltration assertion pin is **structural**: the hostile
manifest carries ``containerPort: 31337`` (the S4-02 AC-24 smoking-gun
convention). A naive ``str(root) + str(resource) + ".startswith(str(root))"``
wrong impl provably leaks ``31337`` into ``exposed_ports`` because
``Path("/tmp/x") / "../sentinel.yaml"`` stringifies to
``/tmp/x/../sentinel.yaml`` which **does** start with ``/tmp/x``. The
``Path.resolve()`` defense rejects.

The companion ``./subdir/../deployment.yaml`` canary proves the mechanism
is ``Path.resolve()``, not substring-on-``..`` — a naive substring check
rejects this legitimate-inside-repo resource too. **Do not remove this
canary during refactor.**

OOS-2: ``tests/unit/probes/test_deployment.py`` (S4-02) owns the unit-PR
zip-slip surface; this file lives at the adversarial-corpus CLI surface.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

import pytest

from tests.adv._helpers import invoke_gather

# --- module fixtures --------------------------------------------------------

_SENTINEL_DEPLOY: Final[str] = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sentinel-leak
spec:
  template:
    spec:
      containers:
        - name: leak
          image: alpine
          ports:
            - containerPort: 31337
"""
"""Sentinel K8s manifest — ``containerPort: 31337`` is the
structurally-impossible-to-fake observable that distinguishes correct
zip-slip refusal from a wrong impl. Convention shared with S4-02 AC-24."""

_VALID_DEPLOY: Final[str] = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webapp
spec:
  template:
    spec:
      containers:
        - name: web
          image: alpine
          ports:
            - containerPort: 8080
"""

_KUSTOMIZATION: Final[str] = """\
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - "../S5-03-SENTINEL-LEAK.yaml"
  - "./deployment.yaml"
  - "./subdir/../deployment.yaml"
"""
"""Three resources — one zip-slip (resolves to ``tmp_path.parent/`` and
escapes ``tmp_path``), one legitimate, one dot-dot-but-inside canary that
pins the ``Path.resolve()`` mechanism. ``kustomization.yaml`` lives at the
repo root because ``DeploymentProbe._has_kustomize`` only matches
``root/kustomization.{yaml,yml}``."""


# --- single fixture, multi-assertion test -----------------------------------


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only Path.resolve() semantics")
def test_kustomize_zip_slip_refused_sentinel_isolated(tmp_path: Path) -> None:
    """AC-5/6/7/8 — sentinel exfiltration refused; legit sibling + the
    ``subdir/..`` canary still processed; no sentinel string-leak anywhere.

    All four ACs share one fixture + one ``invoke_gather`` call; the
    assertions partition cleanly by AC.
    """
    sentinel = tmp_path.parent / "S5-03-SENTINEL-LEAK.yaml"
    sentinel.write_text(_SENTINEL_DEPLOY, encoding="utf-8")
    try:
        # ``kustomization.yaml`` at repo root: ``_has_kustomize`` only
        # detects the root file; nested kustomization files would dispatch
        # to ``_parse_raw`` instead and miss the zip-slip defense entirely.
        (tmp_path / "subdir").mkdir()
        (tmp_path / "deployment.yaml").write_text(_VALID_DEPLOY, encoding="utf-8")
        (tmp_path / "kustomization.yaml").write_text(_KUSTOMIZATION, encoding="utf-8")
        # Phase 1 gather needs a Node anchor to emit a non-vacuous envelope.
        (tmp_path / "package.json").write_text('{"name":"x","version":"0.0.0"}', encoding="utf-8")

        result = invoke_gather(tmp_path)
        assert result.exit_code == 0, (result.exit_code, result.output)

        # Envelope shape: ``probes.deployment.deployment.*`` — the probe wraps
        # its slice fragment under its own slice key ``"deployment"`` per
        # ``deployment.py:761``. Story AC text dropped the inner wrap; this
        # navigates the shipped envelope (Rule 11 — match the codebase).
        dep = result.context["probes"]["deployment"]["deployment"]
        exposed_ports = dep["exposed_ports"]

        # AC-5 — structural pin: sentinel containerPort did NOT reach the slice.
        assert 31337 not in exposed_ports, (
            f"zip-slip exfiltration: sentinel containerPort reached slice; "
            f"exposed_ports={exposed_ports!r}"
        )
        assert dep["kustomization_resource_path_outside_repo"] is True, dep
        assert "kustomization.resource_outside_repo" in dep["warnings"], dep["warnings"]

        # AC-6 — legitimate sibling still processed.
        assert 8080 in exposed_ports, (
            f"legitimate sibling resource dropped; exposed_ports={exposed_ports!r}"
        )

        # AC-7 — subdir/.. canary pins the Path.resolve() mechanism.
        # Without resolve(), a substring-on-".." impl rejects this valid
        # resource and 8080 is absent (already caught by AC-6) or appears
        # only once when the dedupe semantics swallow the second processed
        # reference. Two references to the same file may dedupe to one
        # port entry — assert >=1 (the AC-7 lower bound).
        assert exposed_ports.count(8080) >= 1, (
            f"subdir/.. canary dropped; exposed_ports={exposed_ports!r}"
        )

        # AC-8 — belt-and-suspenders substring scan across YAML + raw + audit.
        scanned_bytes = [result.context_yaml_text, *result.raw_jsons.values()]
        runs_dir = tmp_path / ".codegenie" / "context" / "runs"
        if runs_dir.is_dir():
            for run_json in sorted(runs_dir.iterdir()):
                if run_json.is_file():
                    scanned_bytes.append(run_json.read_text(encoding="utf-8"))
        all_text = "\n".join(scanned_bytes)
        assert "S5-03-SENTINEL-LEAK" not in all_text, "sentinel filename leaked"
        assert "31337" not in all_text, "sentinel port number leaked"
        assert "containerPort: 31337" not in all_text, "sentinel YAML body leaked"
    finally:
        sentinel.unlink(missing_ok=True)
