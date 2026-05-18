from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE6 = ROOT / "docs" / "phases" / "06-sherpa-vuln-loop"
PHASE65 = ROOT / "docs" / "phases" / "06.5-per-task-class-eval-harness"


def test_phase6_design_package_is_complete() -> None:
    expected = {
        "README.md",
        "design-performance.md",
        "design-security.md",
        "design-best-practices.md",
        "critique.md",
        "final-design.md",
        "phase-arch-design.md",
        "High-level-impl.md",
        "ADRs/README.md",
        "ADRs/0001-stable-vuln-remediation-sut-contract.md",
        "ADRs/0002-plugin-local-subgraph-topology.md",
        "ADRs/0003-checkpointed-ledger-replay-boundary.md",
        "stories/README.md",
    }

    missing = sorted(relpath for relpath in expected if not (PHASE6 / relpath).exists())
    assert not missing, f"Phase 6 redesign package missing: {missing}"


def test_phase6_roadmap_and_nav_resolve_to_redesign() -> None:
    roadmap = (ROOT / "docs" / "roadmap.md").read_text()
    mkdocs = (ROOT / "mkdocs.yml").read_text()

    assert "06-sherpa-vuln-loop" in roadmap
    assert "phases/06-sherpa-vuln-loop/README.md" in mkdocs


def test_phase65_canonical_docs_depend_on_stable_sut_contract() -> None:
    canonical_docs = [
        PHASE65 / "final-design.md",
        PHASE65 / "phase-arch-design.md",
        PHASE65 / "High-level-impl.md",
    ]

    for path in canonical_docs:
        text = path.read_text()
        assert "VulnRemediationSut" in text, path
        assert "build_vuln_loop" not in text, path
