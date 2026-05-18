# Changelog

## v1 — HEAD moves forward

This file is the v1 commit's only change relative to v0 — its presence
proves `HEAD != last_indexed_commit` without mutating the indexed
source tree. The `_seed/scip-index.scip` SCIP blob was built against
the v0 tree (`package.json` + `tsconfig.json` + `main.ts` + `src/*.ts`,
6 `.ts` files); `files_indexed == files_in_repo == 6` (no coverage
gap; `IndexHealthProbe` surfaces `CommitsBehind`, not `CoverageGap`).
