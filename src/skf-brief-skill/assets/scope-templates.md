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

**[C] Component Library** — Optimized for UI component libraries with registries, props-based APIs, and design system variants.
- Component registry as primary API surface (not individual exports)
- Props interfaces as API contracts (not function signatures)
- Auto-exclude demo/example/story files (with user confirmation)
- Variant consolidation across design systems

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

### Docs-Only Boundaries

**No source code access.** Scope is defined by the `doc_urls` collected during intent gathering.

- All content derived from external documentation
- No include/exclude patterns — coverage determined by fetched documentation
- All extractions labeled T3 (`[EXT:{url}]` citations)

Prompt: "Any additional documentation URLs to include? Or URLs to exclude from the ones collected?"

### Component Library Boundaries

**Phase 1 — Registry Detection:**

Auto-detect or accept explicit `registry_path` from user. Scan source tree for files matching common registry patterns:
- Files named `registry.ts`, `components.ts`, `index.ts` in `registry/`, `catalog/`, or `components/` directories
- Arrays of objects with `{ id, name, component }` structure and 10+ entries
- Files with `Component[]` type annotations

Present detected registry candidate(s) to user for confirmation.
Prompt: "I found what looks like a component registry at {path} ({count} entries). Is this correct? Or provide the registry path:"

**Phase 2 — Demo/Example Exclusion:**

Auto-detect demo directories and file patterns:
- Directories: `demo/`, `demos/`, `stories/`, `examples/`, `__stories__/`, `storybook/`
- Files: `*.stories.*`, `*.story.*`, `*.example.*`, `*.demo.*`

Present detected patterns to user before applying (do NOT exclude silently).
Prompt: "**Auto-detected {N} demo/example files** in {M} directories. Confirm exclusion? [Y/n] Or adjust patterns:"

**Phase 3 — Variant Selection (if applicable):**

If multiple design system variant directories detected (e.g., `react-shadcn/`, `react-baseui/`, `react-carbon/`):
- Present detected variants with component counts per variant
- User selects primary variant and which variants to include
- Record as `ui_variants` in brief

Prompt: "I detected {count} design system variants: {list with counts}. Which is the primary variant? Include all? [Y/n]"

**Phase 4 — Scope Confirmation:**

Summary showing: component count, excluded demo count, variant summary, include/exclude patterns.
Prompt: "Does this component library scope look right? Adjust before continuing."

## Scripts & Assets Detection (Optional Refinement)

When `scripts_intent` or `assets_intent` is `detect` (default), SKF auto-detects from source directories matching: `scripts/`, `bin/`, `tools/`, `cli/` (for scripts) and `assets/`, `templates/`, `schemas/`, `configs/`, `examples/` (for assets). Detection applies to all scope types except `docs-only`.
