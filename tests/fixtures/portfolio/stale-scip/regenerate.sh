#!/usr/bin/env bash
# Regenerates the stale-scip fixture. See README.md.
# MUST keep HEAD ahead of the parent commit by >= 1.
#
# S7-02 full materialization: v0 commits the full TypeScript source tree
# (package.json + tsconfig.json + main.ts + src/*.ts — 6 .ts files); v1
# commits CHANGELOG.md so HEAD moves forward without mutating the
# indexed tree. The committed binary `_seed/scip-index.scip` was built
# OUT-OF-BAND by scip-typescript against the v0 tree (see README.md
# "Seed-build ritual"). This regen script does NOT invoke scip-typescript
# at runtime; it copies the seed bytes into .codegenie/.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf .git .codegenie

git init -q -b main
git config user.email "fixture@codewizard.local"
git config user.name  "Fixture Bot"

# Pin commit dates so the two commits are byte-identical across runs.
# The exact second is arbitrary; what matters is that two consecutive
# invocations produce the same v0 + v1 SHAs (load-bearing for the
# regen-guard test in tests/unit/fixtures/test_stale_scip_regenerate_guard.py:
# it captures v1's SHA after run 1 and re-invokes with LAST_INDEXED=<that_sha>
# expecting the guard to fire — which only happens if run 2's v1 SHA equals
# run 1's v1 SHA).
export GIT_AUTHOR_DATE="2026-04-26T08:00:00Z"
export GIT_AUTHOR_NAME="Fixture Bot"
export GIT_AUTHOR_EMAIL="fixture@codewizard.local"
export GIT_COMMITTER_DATE="2026-04-26T08:00:00Z"
export GIT_COMMITTER_NAME="Fixture Bot"
export GIT_COMMITTER_EMAIL="fixture@codewizard.local"

# v0 — full source tree. The SCIP index represents this commit.
# LAST_INDEXED will point here.
git add package.json tsconfig.json main.ts src/a.ts src/b.ts src/c.ts src/d.ts src/e.ts
git commit -q -m "v0 — seeded last_indexed_commit (full TypeScript source tree)"
PARENT_COMMIT=$(git rev-parse HEAD)

# v1 — HEAD moves forward. CHANGELOG.md is the only delta; the indexed
# source tree is unchanged so the seed template's
# files_indexed == files_in_repo invariant holds.
git add CHANGELOG.md
git commit -q -m "v1 — HEAD moves forward (CHANGELOG.md only; indexed tree unchanged)"

# Materialize the runtime sibling-slice from the tracked template.
mkdir -p .codegenie/context/raw
sed "s|PARENT_COMMIT|${PARENT_COMMIT}|g" \
  _seed/scip-slice.template.json > .codegenie/context/raw/scip.json
cp _seed/scip-index.scip .codegenie/context/raw/scip-index.scip

# Guard — env-overrideable so `test_regenerate_sh_guard` can force the failing branch.
# Default: the parent of HEAD (which by construction is NOT HEAD itself).
LAST_INDEXED="${LAST_INDEXED:-$(git rev-parse HEAD~1)}"
if [[ "$LAST_INDEXED" == "$(git rev-parse HEAD)" ]]; then
  echo "ERROR: regenerate.sh refuses to set last_indexed_commit == HEAD" >&2
  echo "       This fixture must have HEAD ahead by >= 1. See README.md." >&2
  exit 1
fi
echo "stale-scip fixture regenerated. last_indexed=$PARENT_COMMIT head=$(git rev-parse HEAD)"
