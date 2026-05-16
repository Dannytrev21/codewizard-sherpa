# Vendored tree-sitter grammar binaries

This directory holds the BLAKE3-pinned tree-sitter grammar binaries the
Phase-2 / Phase-3 probes load via `codegenie.grammars.lock.load_and_verify`.

**Current state (S4-03).** The `.so` files in this directory are
**placeholder stubs** — small deterministic binary blobs whose only
contract today is "exists on disk with a BLAKE3 that matches
`tools/grammars.lock`". They are NOT runnable tree-sitter grammars.

**Vendoring discipline.**

- `S4-04` (`TreeSitterImportGraphProbe`) is the first runtime consumer
  and MUST replace these placeholders with real grammar binaries before
  it lands green. The path is:
  1. Clone `tree-sitter/tree-sitter-typescript` at the tag listed in
     `tools/grammars.lock` (`version` field).
  2. `tree-sitter generate && tree-sitter build --output typescript.so`
     for the TypeScript grammar; same for the `javascript` grammar.
  3. Copy the produced `.so` files into this directory.
  4. Run `bash tools/regenerate_grammars_lock.sh` to recompute the
     BLAKE3 pins.
  5. PR description records the upstream release URL + the BLAKE3 the
     vendoring developer computed locally.
- `.gitattributes` declares `*.so` / `*.dylib` binary so git does not
  corrupt them.
- The canonical CI runner is Linux — committed artifact is `.so`.
  Developers on macOS can keep a local `.dylib` for dev loops, but the
  committed lock file pins `.so`.

**Why placeholders ship now.** S4-03 lands the loader/verifier
infrastructure (`codegenie.grammars.lock`) and its `tools/grammars.lock`
manifest so S4-04 can depend on the typed shape without a chicken-and-egg
sequencing problem (the lock file must exist before its consumer). The
BLAKE3 pins for real grammars land with S4-04.
