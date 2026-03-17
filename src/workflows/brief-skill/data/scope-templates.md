# Scope Templates Reference

## Scope Type Options

Present these options to the user for selection:

**[F] Full Library** — Include everything. Best for smaller, focused libraries.
- All public exports, all modules
- Exclude only tests, build artifacts, and internal utilities

**[M] Specific Modules** — Select which modules to include. Best for large libraries where only some parts are relevant.
- You choose which modules/directories
- Fine-grained control over what's in and out

**[P] Public API Only** — Include only the public-facing API surface. Best for libraries with a clear public/private boundary.
- Entry points and exported interfaces only
- Internal implementation excluded

## Boundary Definitions by Scope Type

### Full Library Boundaries

Default inclusions:
- All source files under {main source directory}
- All public modules: {list from analysis}

Default exclusions:
- Test files (`**/*.test.*`, `**/*.spec.*`, `**/test/`, `**/tests/`)
- Build artifacts (`**/dist/`, `**/build/`, `**/target/`)
- Configuration files
- Documentation source files

Prompt: "Any additional exclusions you'd like to add? Or adjustments to these defaults?"

### Specific Modules Boundaries

**Phase 1 — Module selection:**

Present numbered list of modules from step 02 with brief descriptions.
Prompt: "Which modules would you like to include? (Enter numbers, comma-separated):"

**Phase 2 — Granularity within selected modules:**

For selected modules, ask:
- **A)** Everything in those modules (all files)
- **B)** Only public exports from those modules

Prompt: "Any files or patterns to explicitly exclude within these modules?"

### Public API Only Boundaries

**Phase 1 — Export selection:**

Present numbered list of exports/entry points from step 02.
Prompt: "Which of these would you like to include? (Enter numbers, or 'all'):"

**Phase 2 — Confirm exclusions:**

Exclusions will include all internal implementation files, tests, and utilities.
Prompt: "Any additional items you'd like to include or exclude?"
