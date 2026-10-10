<!-- Config: communicate in {communication_language}. -->

# Entry Points by Hand

Step 3 §4b loads this file only when the recipe runner did not diff the entry points: at Quick tier, for extraction by source reading, for a brief whose language no recipe reads, and in the AST Extraction Protocol's fallback. Read the entry points yourself and compare them with the extracted exports, then count `exports_public_api` (the entry points' public names) and `exports_internal` (every other non-underscore export) for step 5 §4:

- **Python:** Read `{source_root}/__init__.py`: extract imports to build the public export list. Compare against AST results:
  - In AST but not entry point → mark as internal (exclude from `metadata.json` exports)
  - In entry point but not AST → flag as extraction gap (trace via re-export protocol)
- **TypeScript/JS:** Read `index.ts`/`index.js`: same comparison logic.
- **Rust:** Read `lib.rs`: extract `pub use` items. Same logic. **Go:** Scan for exported (capitalized) identifiers.
- **A submodule the entry point exports by name** (`from . import sub`, `export * as ns`, a Rust `pub mod`) counts as the names its module passes on, each name and file once, as the recipe runner counts it.

**Multi-entry packages (`exports` map / declaration-file entry points).** A single per-language entry-point read misses public surface that a package ships through its `package.json` `exports` map, especially committed `.d.ts` / `.d.mts` declaration files that resolve **outside** the conventional source dir (e.g. a monorepo package whose `./macro` subpath maps to `macro/index.d.mts`, listed in `files[]` but not under `src/`). When the in-scope package declares an `exports` map:

- Resolve each `exports` subpath to its target file and treat that file, and any committed `.d.ts` / `.d.mts` declaration it resolves to, as an authoritative public entry point, reading it the same way as the primary barrel above even when it lives outside `src/`.
- If a resolved `exports` subpath target falls **outside** the brief's `scope.include` globs, surface a note: `"warn: public entry point {path} (exports subpath '{subpath}') resolves outside scope.include: widen scope.include before extraction, or this surface stays undocumented while exports_public_api still counts it, so public_api_coverage drops (only effective_denominator, for the curated-subset shapes, leaves it out)."` Widening `scope.include` here keeps the documented surface aligned with the `effective_denominator` that compile.md §4 derives from those same globs, without mid-run scope surgery.

Use the entry point as the authoritative source for `metadata.json`'s `exports[]` array.

**If entry point is missing or unreadable:** Skip validation with a warning.
