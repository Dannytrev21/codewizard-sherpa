"""S6-06 — property-based totality tests for per-scanner classifiers.

Each scanner declares a private tagged-union ``ScannerAttempt`` and a
pure classifier. The classifier MUST be total (every input → exactly
one ``ScannerOutcome``, never raises) and side-effect-free.

T3 (mirror S5-04 T3): a property-based test is the kernel of the
mutation-resistance argument. A stub that always returned
``ScannerRan(findings=[])`` would pass most happy-path tests but would
fail the totality property as soon as Hypothesis drew a
``_ProcessExited(exit_code=2, ...)``.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.layer_g.ast_grep import (
    _classify_ast_grep_outcome,
)
from codegenie.probes.layer_g.ast_grep import (
    _ProcessExited as AgExited,
)
from codegenie.probes.layer_g.ast_grep import (
    _ProcessTimedOut as AgTimedOut,
)
from codegenie.probes.layer_g.ast_grep import (
    _ToolMissing as AgMissing,
)
from codegenie.probes.layer_g.gitleaks import (
    _classify_gitleaks_outcome,
)
from codegenie.probes.layer_g.gitleaks import (
    _ProcessExited as GlExited,
)
from codegenie.probes.layer_g.gitleaks import (
    _ProcessTimedOut as GlTimedOut,
)
from codegenie.probes.layer_g.gitleaks import (
    _ToolMissing as GlMissing,
)
from codegenie.probes.layer_g.ripgrep_curated import (
    _classify_ripgrep_outcome,
)
from codegenie.probes.layer_g.ripgrep_curated import (
    _ProcessExited as RgExited,
)
from codegenie.probes.layer_g.ripgrep_curated import (
    _ProcessTimedOut as RgTimedOut,
)
from codegenie.probes.layer_g.ripgrep_curated import (
    _ToolMissing as RgMissing,
)
from codegenie.probes.layer_g.semgrep import (
    _classify_semgrep_outcome,
)
from codegenie.probes.layer_g.semgrep import (
    _ProcessExited as SgExited,
)
from codegenie.probes.layer_g.semgrep import (
    _ProcessTimedOut as SgTimedOut,
)
from codegenie.probes.layer_g.semgrep import (
    _ToolMissing as SgMissing,
)

# ---------------------------------------------------------------------------
# Semgrep
# ---------------------------------------------------------------------------


@given(
    exit_code=st.integers(min_value=-128, max_value=255),
    stdout=st.binary(max_size=4096),
    stderr_tail=st.text(max_size=512),
)
def test_semgrep_classifier_total_on_process_exited(exit_code, stdout, stderr_tail) -> None:
    outcome, _findings, _rules, _files = _classify_semgrep_outcome(
        SgExited(exit_code=exit_code, stdout=stdout, stderr_tail=stderr_tail)
    )
    assert isinstance(outcome, (ScannerRan, ScannerSkipped, ScannerFailed))


def test_semgrep_classifier_total_on_tool_missing() -> None:
    outcome, _, _, _ = _classify_semgrep_outcome(SgMissing())
    assert isinstance(outcome, ScannerSkipped)
    assert outcome.reason == "tool_missing"


def test_semgrep_classifier_total_on_timeout() -> None:
    outcome, _, _, _ = _classify_semgrep_outcome(SgTimedOut())
    assert isinstance(outcome, ScannerFailed)
    assert outcome.exit_code == 124


# ---------------------------------------------------------------------------
# AstGrep
# ---------------------------------------------------------------------------


@given(
    exit_code=st.integers(min_value=-128, max_value=255),
    stdout=st.binary(max_size=4096),
    stderr_tail=st.text(max_size=512),
)
def test_ast_grep_classifier_total_on_process_exited(exit_code, stdout, stderr_tail) -> None:
    outcome, _findings = _classify_ast_grep_outcome(
        AgExited(exit_code=exit_code, stdout=stdout, stderr_tail=stderr_tail)
    )
    assert isinstance(outcome, (ScannerRan, ScannerSkipped, ScannerFailed))


def test_ast_grep_classifier_total_on_tool_missing() -> None:
    outcome, _ = _classify_ast_grep_outcome(AgMissing())
    assert isinstance(outcome, ScannerSkipped)


def test_ast_grep_classifier_total_on_timeout() -> None:
    outcome, _ = _classify_ast_grep_outcome(AgTimedOut())
    assert isinstance(outcome, ScannerFailed)


# ---------------------------------------------------------------------------
# Ripgrep
# ---------------------------------------------------------------------------


@given(
    exit_code=st.integers(min_value=-128, max_value=255),
    stdout=st.binary(max_size=4096),
    stderr_tail=st.text(max_size=512),
)
def test_ripgrep_classifier_total_on_process_exited(exit_code, stdout, stderr_tail) -> None:
    outcome, _findings = _classify_ripgrep_outcome(
        RgExited(exit_code=exit_code, stdout=stdout, stderr_tail=stderr_tail)
    )
    assert isinstance(outcome, (ScannerRan, ScannerSkipped, ScannerFailed))


def test_ripgrep_classifier_total_on_tool_missing() -> None:
    outcome, _ = _classify_ripgrep_outcome(RgMissing())
    assert isinstance(outcome, ScannerSkipped)


def test_ripgrep_classifier_total_on_timeout() -> None:
    outcome, _ = _classify_ripgrep_outcome(RgTimedOut())
    assert isinstance(outcome, ScannerFailed)


# ---------------------------------------------------------------------------
# Gitleaks (S6-07)
# ---------------------------------------------------------------------------


@given(
    exit_code=st.integers(min_value=-128, max_value=255),
    stdout=st.binary(max_size=4096),
    stderr_tail=st.text(max_size=512),
)
def test_gitleaks_classifier_total_on_process_exited(exit_code, stdout, stderr_tail) -> None:
    outcome, _findings, _raw = _classify_gitleaks_outcome(
        GlExited(exit_code=exit_code, stdout=stdout, stderr_tail=stderr_tail)
    )
    assert isinstance(outcome, (ScannerRan, ScannerSkipped, ScannerFailed))


def test_gitleaks_classifier_total_on_tool_missing() -> None:
    outcome, _findings, raw = _classify_gitleaks_outcome(GlMissing())
    assert isinstance(outcome, ScannerSkipped)
    assert outcome.reason == "tool_missing"
    assert raw is None


def test_gitleaks_classifier_total_on_timeout() -> None:
    outcome, _findings, raw = _classify_gitleaks_outcome(GlTimedOut())
    assert isinstance(outcome, ScannerFailed)
    assert outcome.exit_code == 124
    assert raw is None
