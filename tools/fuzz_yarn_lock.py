"""Local pre-PR fuzz harness for ``_lockfiles/_yarn._parse_handrolled``.

Required by S3-03 AC-16 + High-level-impl.md §"Step 3" Implementation-level
risks #4: "adversarial fuzzing in S5-02 is the CI gate but not the first
defense." This script byte-mutates a real ``yarn.lock`` ≥ 1000 times under a
1-second-per-iteration ``signal.alarm`` timeout and prints a summary line
the implementer pastes into the PR body.

Lives at ``tools/`` (not ``tests/``) so pytest does not collect it; it is
intentionally throwaway. The corpus for adversarial CI is S5-02's job; this
harness is implementer-side first defense.

Targets ``_parse_handrolled`` directly (functional core / imperative shell —
the pure function is testable without filesystem I/O).
"""

from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from codegenie.probes._lockfiles._yarn import _parse_handrolled  # noqa: E402


class FuzzTimeout(Exception):
    """Raised by the SIGALRM handler when a single iteration exceeds the cap."""


def _alarm_handler(signum: int, frame: object) -> NoReturn:
    raise FuzzTimeout("iteration exceeded the per-iteration wall-clock cap")


def _mutate(body: bytes, rng: random.Random) -> bytes:
    """Return ``body`` with a small number of random byte mutations."""
    if not body:
        return body
    out = bytearray(body)
    n_mutations = rng.randint(1, max(1, len(out) // 32))
    for _ in range(n_mutations):
        op = rng.choice(("flip", "delete", "insert", "duplicate-line"))
        if op == "flip" and out:
            i = rng.randrange(len(out))
            out[i] ^= rng.randint(1, 255)
        elif op == "delete" and out:
            i = rng.randrange(len(out))
            del out[i]
        elif op == "insert":
            i = rng.randrange(len(out) + 1)
            out.insert(i, rng.randint(0, 255))
        elif op == "duplicate-line" and b"\n" in out:
            text = bytes(out)
            lines = text.split(b"\n")
            j = rng.randrange(len(lines))
            lines.insert(j, lines[j])
            out = bytearray(b"\n".join(lines))
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="Number of fuzz iterations (default: 1000).",
    )
    parser.add_argument(
        "--per-iteration-timeout-seconds",
        type=int,
        default=1,
        help="Per-iteration wall-clock cap (SIGALRM).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducibility (default: time-based).",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=REPO_ROOT / "tests" / "fixtures" / "node_yarn_legacy" / "yarn.lock",
        help="Seed yarn.lock to mutate.",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    body = args.corpus.read_bytes()

    signal.signal(signal.SIGALRM, _alarm_handler)

    n_ok = 0
    n_translated = 0  # raised an exception we'd translate (UnicodeDecodeError, ValueError)
    n_unexpected = 0  # any other exception type — investigate
    n_timeout = 0
    worst_seconds = 0.0
    worst_iteration = -1

    for i in range(args.iterations):
        mutant = _mutate(body, rng)
        signal.alarm(args.per_iteration_timeout_seconds)
        start = time.perf_counter()
        try:
            _parse_handrolled(mutant)
            n_ok += 1
        except (UnicodeDecodeError, ValueError):
            n_translated += 1
        except FuzzTimeout:
            n_timeout += 1
        except BaseException as exc:  # noqa: BLE001 — fuzz harness wants every leak surfaced
            n_unexpected += 1
            print(  # noqa: T201 — CLI fuzz harness; structlog is overkill for tools/
                f"[iter {i}] UNEXPECTED {type(exc).__name__}: {exc!r}",
                file=sys.stderr,
            )
        finally:
            signal.alarm(0)
            elapsed = time.perf_counter() - start
            if elapsed > worst_seconds:
                worst_seconds = elapsed
                worst_iteration = i

    print(  # noqa: T201 — CLI fuzz harness; structlog is overkill for tools/
        f"fuzz_yarn_lock.py: iterations={args.iterations} "
        f"ok={n_ok} translated={n_translated} unexpected={n_unexpected} "
        f"timeouts={n_timeout} worst_iter={worst_iteration} "
        f"worst_wall_clock_seconds={worst_seconds:.4f}"
    )
    return 0 if (n_unexpected == 0 and n_timeout == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
