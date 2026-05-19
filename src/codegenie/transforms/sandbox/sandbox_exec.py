"""macOS Adapter for the :class:`SubprocessJail` Port — S4-03.

Wraps every child invocation in ``sandbox-exec -f <generated.sb>`` per
ADR-0006 §Decision. The ``.sb`` profile is rendered per call from the
packaged static template at
``codegenie.transforms.sandbox.templates/macos-npm.sb``; the rendered
file is written to a per-call ``tempfile.NamedTemporaryFile`` under
``spec.cwd`` and unlinked in ``try/finally``.

**Deprecation acceptance.** ADR-0006 §Tradeoffs row 3 names this
explicitly: macOS ``sandbox-exec`` is deprecation-flagged by Apple, and
Phase 5 substitutes Lima/DinD. Phase 3 carries the tech-debt: we ship a
working substrate on operator laptops (most of which are macOS), keep
the deprecation documented at the symbol, and let Phase 5 own the
substitution. Module is gated to macOS 14+ via
:class:`SubstrateUnsupportedError`; older releases must wait for Phase 5.

**Chokepoint.** All subprocess invocations route through
:func:`codegenie.exec.run_allowlisted`. The Adapter does not call
:func:`subprocess.run` / :func:`os.system` / :func:`os.execv` / any
async-subprocess primitive; an AST fence in
``test_sandbox_exec_unit.py`` pins this.

**Kernel consumption.** Variant translation delegates to the
substrate-agnostic :func:`codegenie.transforms.sandbox._classify.classify_outcome`
kernel that S4-02 extracted. The macOS-specific
:func:`_parse_sandbox_denial` extracts ``host`` from ``sandbox-exec``
stderr (format: ``Sandbox: <proc>(<pid>) deny(1) network-outbound
<host>:<port>``). A substrate parse-error pattern (``Sandbox: ... error:``)
maps to :class:`~codegenie.transforms.sandbox_jail.JailSetupFailed`
with ``reason="kernel-setup-failed"``.

ADRs honoured: phase-3 ADR-0006 (this Adapter), ADR-0010 (sum-type
``match`` + ``assert_never``), ADR-0011 (``importlib.resources``
precedent — packaged static asset, wheel-install survival), ADR-0012
(``sandbox-exec`` admitted to ``ALLOWED_BINARIES`` by S4-05).
"""

from __future__ import annotations

import functools
import platform
import re
import string
import sys
import tempfile
import time
import typing
import urllib.parse
import uuid
from importlib import resources
from pathlib import Path
from typing import Final

from codegenie.exec import ProcessResult, run_allowlisted
from codegenie.transforms.sandbox._classify import (
    ClassifierSignals,
    classify_outcome,
)
from codegenie.transforms.sandbox_jail import (
    DenyAll,
    JailedSubprocessResult,
    JailedSubprocessSpec,
    JailSetupFailed,
    NetworkDenied,
    NetworkPolicy,
    RegistryAllowlist,
)
from codegenie.types.identifiers import RegistryUrl

__all__ = [
    "Hostname",
    "ProfilePlaceholderUnresolved",
    "SandboxExecAdapter",
    "SubstrateUnsupportedError",
    "classify_outcome",
]


# AC-29: Hexagonal-Port symmetry made observable at the file boundary.
# The same frozenset MUST appear in ``bwrap.py``; a meta-test pins identity.
_HELPER_VERBS: Final[frozenset[str]] = frozenset({"build_argv", "render", "translate"})


# Substrate stderr signatures.
#
# Network-outbound denial (AC-7): ``Sandbox: npm(1234) deny(1)
# network-outbound github.com:443``.
_SANDBOX_DENY_NETWORK_RE: Final[re.Pattern[bytes]] = re.compile(
    rb"Sandbox:[^\n]*deny[^\n]*network-outbound\s+([A-Za-z0-9.\-]+):\d+",
)
# Substrate parse / setup error (AC-21): ``Sandbox: sandbox-exec error: parse failure at line 3``.
_SANDBOX_SETUP_ERROR_RE: Final[re.Pattern[bytes]] = re.compile(
    rb"Sandbox:[^\n]*error:",
)

# Hostname validation — DNS-label charset only, no schemes / paths.
_HOSTNAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9.\-]+$")

# Placeholder residual regex (AC-28).
_RESIDUAL_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"\$[A-Z_]+")

# Minimum supported macOS version (AC-27). Phase 5 substitutes for <14.0.
_MIN_MACOS_MAJOR: Final[int] = 14


Hostname = typing.NewType("Hostname", str)
"""Validated DNS-host newtype (AC-25). Smart-constructor:
:func:`_extract_hostname`. Consumers must accept ``Hostname`` — passing
a raw ``str`` is a typecheck error (a subprocess-mypy negative fixture
pins this)."""


class SubstrateUnsupportedError(RuntimeError):
    """Raised at :class:`SandboxExecAdapter` construction on macOS < 14.

    Phase 5 (``05-ADR-0004``) substitutes Lima/DinD on macOS; until that
    lands, the codebase refuses to silently degrade to "no jail" on
    older OS releases. Rule 12: fail loud, fail typed.
    """

    def __init__(self, version: str, replacement: str) -> None:
        super().__init__(
            f"sandbox-exec adapter requires macOS {_MIN_MACOS_MAJOR}+ "
            f"(observed {version!r}). {replacement}"
        )
        self.version = version
        self.replacement = replacement


class ProfilePlaceholderUnresolved(RuntimeError):
    """Raised when ``_render_profile`` finds a ``$NAME`` token surviving
    ``string.Template.safe_substitute`` (AC-28).

    A typo in a placeholder name in the template (e.g., adding ``$JAILS``
    where the substitute call expects ``$JAIL``) is exactly the failure
    Rule 12 names: fail loud at the boundary, do not hand a corrupt
    profile to ``sandbox-exec``.
    """

    def __init__(self, token: str) -> None:
        super().__init__(
            f"Unresolved profile placeholder {token!r} survived "
            f"string.Template.safe_substitute — typo in template or "
            f"missing substitute argument."
        )
        self.token = token


# ---------------------------------------------------------------------------
# Packaged template — loaded once via ``importlib.resources`` (AC-26).
# ---------------------------------------------------------------------------


@functools.cache
def _load_template() -> string.Template:
    """Load the packaged ``.sb`` template (AC-26).

    Uses ``importlib.resources.files`` so the template survives
    wheel-install — the source repo's working directory is irrelevant.
    """
    text = (
        resources.files("codegenie.transforms.sandbox.templates")
        .joinpath("macos-npm.sb")
        .read_text(encoding="utf-8")
    )
    return string.Template(text)


# ---------------------------------------------------------------------------
# Pure renderer — no I/O. Tested via property + parametric fixtures.
# ---------------------------------------------------------------------------


def _extract_hostname(url: RegistryUrl) -> Hostname:
    """Round-trip a strict-``https://`` :class:`RegistryUrl` through
    :func:`urllib.parse.urlparse`, validate against :data:`_HOSTNAME_RE`,
    return a :class:`Hostname` newtype (AC-25).

    Raises ``ValueError`` on missing / malformed host so a typo'd
    allowlist entry fails loud at render time.
    """
    parsed = urllib.parse.urlparse(str(url))
    host = parsed.hostname
    if not host or not _HOSTNAME_RE.match(host):
        raise ValueError(
            f"sandbox_exec.hostname_invalid: {str(url)!r} does not parse "
            f"to a valid DNS host (got {host!r})."
        )
    return Hostname(host)


def _extract_port(url: RegistryUrl) -> int:
    """Return the URL port; default to ``443`` (the
    :class:`RegistryUrl` smart-constructor pins ``https://`` so 443 is
    the only correct default)."""
    parsed = urllib.parse.urlparse(str(url))
    return parsed.port if parsed.port is not None else 443


def _render_allow_network_clause(host: Hostname, port: int) -> str:
    """Compose one ``(allow network* (remote tcp "host:port"))`` clause
    (AC-25 consumer of :class:`Hostname`)."""
    return f'(allow network* (remote tcp "{host}:{port}"))'


def _render_allowlist_clauses(network: NetworkPolicy) -> str:
    """Dispatch on the :data:`NetworkPolicy` sum (AC-24).

    Sorted host iteration (AC-17 determinism — ``frozenset`` iteration
    is not order-stable). ``assert_never`` in the wildcard arm fences
    mypy exhaustiveness; the negative meta-test exercises the runtime
    raise.
    """
    match network:
        case DenyAll():
            return ""
        case RegistryAllowlist(hosts=hosts):
            clauses: list[str] = []
            for url in sorted(hosts):
                host = _extract_hostname(url)
                port = _extract_port(url)
                clauses.append(_render_allow_network_clause(host, port))
            return "\n".join(clauses)
        case _:  # pragma: no cover — assert_never fences mypy + runtime
            typing.assert_never(network)


def _render_profile(template: string.Template, spec: JailedSubprocessSpec) -> str:
    """Pure profile renderer (AC-3 / AC-17 / AC-28).

    ``str(spec.cwd)`` — NOT ``str(spec.cwd.absolute)``: ``Path.absolute``
    is a method, not a property; the bare ``str`` repr suffices and
    :class:`SandboxedPath` is already absolute by construction.
    """
    clauses = _render_allowlist_clauses(spec.network)
    rendered = template.safe_substitute(
        JAIL=str(spec.cwd),
        ALLOWLIST_HOSTS=clauses,
    )
    match = _RESIDUAL_PLACEHOLDER_RE.search(rendered)
    if match is not None:
        raise ProfilePlaceholderUnresolved(match.group(0))
    return rendered


def _parse_sandbox_denial(stderr: bytes) -> Hostname | None:
    """Extract the denied host from ``sandbox-exec`` stderr or ``None``
    (AC-7 / AC-23).

    Format: ``Sandbox: <proc>(<pid>) deny(1) network-outbound <host>:<port>``.
    On a typo / missing host, returns ``None`` — the caller falls through
    to the kernel classifier.
    """
    match = _SANDBOX_DENY_NETWORK_RE.search(stderr)
    if match is None:
        return None
    host = match.group(1).decode("ascii", errors="replace")
    if not _HOSTNAME_RE.match(host):
        return None
    return Hostname(host)


def _is_substrate_setup_error(stderr: bytes) -> bool:
    """True iff stderr names a ``sandbox-exec`` substrate-level error
    (AC-21). Profile parse failures land here, not in the network-policy
    bucket."""
    return _SANDBOX_SETUP_ERROR_RE.search(stderr) is not None


# ---------------------------------------------------------------------------
# Adapter — Port conformance is structural (S4-01 forbids
# ``@runtime_checkable``); AC-2 pins the signature + dispatch.
# ---------------------------------------------------------------------------


class SandboxExecAdapter:
    """macOS :class:`SubprocessJail` Adapter.

    Structural conformance to the Port is verified by mypy + an
    ``inspect.signature`` test (AC-2); the Port is intentionally **not**
    ``@runtime_checkable`` (S4-01 AC-2). Construction enforces the
    macOS 14+ floor (AC-27) — older releases raise
    :class:`SubstrateUnsupportedError` rather than silently producing
    a no-op jail.

    Statelessness: no instance fields, no module-level mutable globals
    (AC-22). The template loader is ``@functools.cache``-wrapped — a
    typed immutable, observably identical across instances.
    """

    def __init__(self) -> None:
        if sys.platform == "darwin":
            ver_str = platform.mac_ver()[0]
            if ver_str:
                parts = ver_str.split(".")
                try:
                    major = int(parts[0])
                except ValueError as exc:  # pragma: no cover — platform contract
                    raise SubstrateUnsupportedError(
                        ver_str, "Phase 5 Lima/DinD substitutes here"
                    ) from exc
                if major < _MIN_MACOS_MAJOR:
                    raise SubstrateUnsupportedError(ver_str, "Phase 5 Lima/DinD substitutes here")

    async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
        """Run *spec.cmd* inside a ``sandbox-exec`` jail.

        Every failure mode rides home as a typed
        :data:`JailedSubprocessResult` variant; this method never raises
        across the Port boundary (AC-16).
        """
        profile_path: str | None = None
        process_result: ProcessResult | None = None
        raised: BaseException | None = None
        start_monotonic = time.monotonic()

        try:
            # Render the profile (pure). A typo in placeholder names
            # fails loud via ``ProfilePlaceholderUnresolved`` — we catch
            # it here to honour AC-16 (no exception across the boundary).
            try:
                rendered = _render_profile(_load_template(), spec)
            except (ProfilePlaceholderUnresolved, ValueError) as exc:
                return JailSetupFailed(
                    kind="jail_setup_failed",
                    reason="kernel-setup-failed",
                    detail=str(exc),
                )

            # Write profile to per-call tempfile under spec.cwd; AC-20
            # ensures uniqueness so concurrent runs never share a path.
            # Unwrap the SandboxedPath capability to its underlying Path
            # at the OS-call boundary (S4-04 flipped the alias from
            # ``pathlib.Path`` to a Pydantic ``BaseModel``).
            cwd_path = spec.cwd.absolute
            try:
                profile_path = _write_profile(cwd_path, rendered)
            except OSError as exc:
                return JailSetupFailed(
                    kind="jail_setup_failed",
                    reason="kernel-setup-failed",
                    detail=f"profile write: {exc}",
                )

            argv = _build_argv(profile_path, spec.cmd)
            env_extra: dict[str, str] = dict(spec.env.to_env_mapping())

            try:
                process_result = await run_allowlisted(
                    argv,
                    cwd=cwd_path,
                    timeout_s=spec.time_budget_s,
                    env_extra=env_extra,
                )
            except BaseException as exc:  # noqa: BLE001 — Port boundary
                raised = exc

            elapsed_s = time.monotonic() - start_monotonic

            # Substrate-specific pre-classification (AC-7 / AC-21). The
            # kernel handles libc-flavoured network errors and the
            # SIGKILL discriminator; macOS substrate stderr signatures
            # land here first.
            if (
                process_result is not None
                and process_result.returncode != 0
                and process_result.stderr
            ):
                stderr = process_result.stderr
                if _is_substrate_setup_error(stderr):
                    return JailSetupFailed(
                        kind="jail_setup_failed",
                        reason="kernel-setup-failed",
                        detail=_excerpt(stderr),
                    )
                host = _parse_sandbox_denial(stderr)
                if host is not None:
                    return NetworkDenied(
                        kind="network_denied",
                        host=str(host),
                    )

            allowlist = _hosts_for_classifier(spec.network)
            signals = ClassifierSignals(elapsed_s=elapsed_s, peak_rss_mib=0)

            return classify_outcome(
                process_result=process_result,
                raised_exception=raised,
                spec_cmd=spec.cmd,
                spec_time_budget_s=spec.time_budget_s,
                spec_memory_mib=spec.memory_mib,
                spec_network_hosts=allowlist,
                signals=signals,
            )
        finally:
            # AC-19: cleanup is unconditional.
            if profile_path is not None:
                try:
                    Path(profile_path).unlink(missing_ok=True)
                except OSError:  # pragma: no cover — best-effort
                    pass


# ---------------------------------------------------------------------------
# Module-local helpers (named to mirror bwrap.py for AC-29 parity).
# ---------------------------------------------------------------------------


def _build_argv(profile_path: str, cmd: tuple[str, ...]) -> list[str]:
    """Compose the ``sandbox-exec`` argv (AC-5). Pure."""
    return ["sandbox-exec", "-f", profile_path, *cmd]


def _write_profile(cwd: Path, rendered: str) -> str:
    """Write *rendered* to a per-invocation tempfile under *cwd* and
    return the absolute path (AC-19 / AC-20).

    ``tempfile.NamedTemporaryFile`` with ``delete=False`` gives the
    Adapter ownership of cleanup; the embedded ``uuid4`` prefix
    guarantees unique paths under ``asyncio.gather`` concurrency.
    """
    # Pre-mktemp uuid guarantees uniqueness even if the tempfile
    # implementation re-uses inode-name salt under load.
    suffix = f".{uuid.uuid4().hex[:8]}.sb"
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(cwd),
        prefix="codegenie-sandbox-",
        suffix=suffix,
        delete=False,
    )
    try:
        handle.write(rendered)
        handle.flush()
    finally:
        handle.close()
    return handle.name


def _hosts_for_classifier(network: NetworkPolicy) -> frozenset[str] | None:
    """Translate the network sum to the classifier's
    ``spec_network_hosts`` argument shape. ``None`` for ``DenyAll``
    (any host denied), ``frozenset[str]`` of full URLs for
    ``RegistryAllowlist``."""
    match network:
        case DenyAll():
            return None
        case RegistryAllowlist(hosts=hosts):
            return frozenset(str(h) for h in hosts)
        case _:  # pragma: no cover — assert_never fences mypy + runtime
            typing.assert_never(network)


_STDERR_EXCERPT_LIMIT: Final[int] = 512


def _excerpt(stderr: bytes) -> str:
    """Decode + truncate stderr for :class:`JailSetupFailed.detail`.
    Bounded so a chatty substrate cannot inflate the result envelope."""
    decoded = stderr.decode("utf-8", errors="replace").strip()
    if len(decoded) <= _STDERR_EXCERPT_LIMIT:
        return decoded
    return decoded[: _STDERR_EXCERPT_LIMIT - 3] + "..."
