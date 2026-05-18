#!/usr/bin/env bash
# Regenerates the monorepo-pnpm fixture. See README.md.
#
# `pnpm` is NOT in ALLOWED_BINARIES (per ADR-0001 / S1-06). The
# `pnpm-lock.yaml` shipped alongside this fixture is **hand-authored
# bytes** generated OUT-OF-BAND on a contributor's local box (one-time
# per dependency-version bump). This regen script is `mkdir`/coreutils-
# only — it materializes any directory skeleton that is regenerated and
# asserts invariants.
set -euo pipefail
cd "$(dirname "$0")"

# Ensure the package directory tree exists (idempotent — these are all
# committed; this is here so the regen contract is "running this script
# leaves the working tree in a known state, including dir-only entries
# that git would normally not create".)
mkdir -p packages/lib-a/src packages/lib-b/src packages/app/src .github/workflows

echo "monorepo-pnpm fixture regenerated (pnpm-lock.yaml is hand-authored bytes;"
echo "  pnpm install is NOT run at regen time — see README.md)."
