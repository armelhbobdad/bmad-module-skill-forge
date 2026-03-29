---
name: 'step-03d-component-extraction'
description: 'Component-library extraction strategy — registry detection, props-first extraction, variant consolidation, demo exclusion'
returnToStep: './step-03-extract.md'
extractionPatternsData: '../data/extraction-patterns.md'
---

# Step 3d: Component Library Extraction

## STEP GOAL:

When `scope.type: "component-library"`, perform specialized extraction that treats the component registry as the primary API surface and props interfaces as API contracts. This step replaces the standard AST extraction flow (step-03 sections 4-4c) and returns control to step-03 section 5 (Build Extraction Inventory).

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing component-library-specialized extraction
- ✅ Zero hallucination tolerance — every extracted item must trace to source code
- ✅ Component registry is the source of truth for the API surface
- ✅ Props interfaces are the API contracts, not function signatures

### Step-Specific Rules:

- 🎯 Focus ONLY on extracting component catalog, props interfaces, and shared types
- 🚫 FORBIDDEN to compile SKILL.md content — that is step-05
- 🚫 FORBIDDEN to write any output files — extraction stays in context
- 🚫 FORBIDDEN to include content that cannot be cited to a source location
- ⚒️ Every extracted item MUST have a provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

## CONTEXT BOUNDARIES:

- Available: brief_data (including `scope.registry_path`, `scope.ui_variants`, `scope.demo_patterns` if present), tier, source_root (may be `temp_path` from ephemeral clone for remote repos — use the working source path resolved in step-03 section 2a), filtered file list from step-03 section 2, CCC discovery results (if available from step-03 section 2a)
- Focus: Component-specific extraction and inventory building
- Limits: Do NOT compile, assemble, or write output
- Dependencies: Source code accessible (resolved in step-03 section 2a — ephemeral clone for remote repos), scope filters already applied

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### Phase 1: Demo/Example Exclusion

Before extraction, identify and exclude demo/example files to avoid inflating export counts.

**If `scope.demo_patterns` is specified in the brief:** Use those patterns directly.

**Otherwise, auto-detect:**

1. Scan the filtered file list for directories matching: `demo/`, `demos/`, `stories/`, `examples/`, `__stories__/`, `storybook/`
2. Scan for file patterns matching: `*.stories.*`, `*.story.*`, `*.example.*`, `*.demo.*`
3. Count matches per pattern category

**User confirmation required:**

"**Auto-detected {N} demo/example files** in {M} directories matching these patterns:
{list detected patterns with counts}

Confirm exclusion? [Y/n] Or adjust patterns:"

Wait for user response. Apply confirmed patterns to the exclude list. Record `demo_files_excluded: {count}` in context.

Update the filtered file list by removing excluded demo files before proceeding.

### Phase 2: Registry Detection

The component registry is the primary API surface for component libraries.

**If `scope.registry_path` is specified in the brief:**

Read the specified file directly. Parse it as described below.

**Otherwise, auto-detect:**

1. Search the filtered file list for files matching these patterns (in priority order):
   - Files named `registry.ts`, `registry.tsx`, `registry.js` in any directory
   - Files named `components.ts`, `components.tsx` in `registry/`, `catalog/`, or `components/` directories
   - Files named `index.ts`, `index.tsx` in `registry/` or `catalog/` directories

2. For each candidate, read the file and look for:
   - Arrays of objects with fields like `id`, `name`, `component`, `category`
   - Type annotations containing `Component[]` or similar array types
   - 10+ entries to qualify as a registry (reject small arrays)

3. **Confidence scoring** for each candidate:
   - +3 points: Contains `id` field per entry
   - +2 points: Contains `name` or `component` field per entry
   - +2 points: Contains `category` or `tags` field per entry
   - +1 point: Located in a `registry/` or `catalog/` directory
   - +1 point: Has 20+ entries
   - Minimum threshold: 5 points to qualify

4. **User confirmation required:**

"**Registry candidate detected** at `{path}` (confidence: {score}/9, {count} entries).

Sample entries:
{show 3-5 sample entries with id, name, category}

Is this the component registry? [Y/n] Or provide the correct path:"

Wait for user response.

**If no registry found and no `registry_path` in brief:**

"**No component registry detected.** Component-library extraction works best with a registry file. Options:
- **[P]** Provide the registry file path
- **[S]** Skip registry — proceed with standard props-first extraction only"

Wait for user response.

### Phase 3: Parse Registry

If a registry was confirmed, parse it into `component_catalog[]`:

**Per-component entry:**

- `id` — registry key (used for CLI `add` command)
- `name` — display name (PascalCase)
- `description` — from registry or empty
- `category` — from registry field or directory structure
- `available_in[]` — which design system variants include this component
- `code_paths[]` — source file path for each variant
- `tags[]` — from registry or empty
- Provenance citation: `[SRC:{registry_file}:L{line}]`

Display: "**Parsed component catalog: {N} components across {M} categories.**"

**If no registry:** Set `component_catalog: []` and proceed to Phase 4.

### Phase 4: Props-First Extraction

Extract props interfaces as the primary API contracts, then link to components.

**Step 1 — Extract Props interfaces:**

Load `{extractionPatternsData}` and use the component-library-specific patterns.

Using AST tools (Forge/Deep) or source reading (Quick):

```yaml
# React/TypeScript props interfaces
id: react-props-interfaces
language: typescript
rule:
  pattern: 'export interface $NAME { $$$ }'
constraints:
  NAME:
    regex: '.*Props$'
```

For each `*Props` interface found:
- Extract all fields with types, optionality, and default values
- Extract JSDoc descriptions per field (if present)
- Record: interface name, fields[], source file, line number
- Provenance: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`

**Step 2 — Extract component exports:**

```yaml
# React component exports (PascalCase)
id: react-component-exports
language: tsx  # Use 'tsx' for .tsx files, 'typescript' for .ts files
rule:
  pattern: 'export function $NAME($$$PARAMS)'
constraints:
  NAME:
    regex: '^[A-Z]'
```

Also run `export const $NAME` patterns for arrow function components.

For each component export: record name, source file, line number. Do NOT document the function signature in detail (it's always `(props: XProps) => JSX.Element`).

**Step 3 — Link Props to Components:**

Use a 3-level fallback chain:

1. **Naming convention (primary):** Match `FooProps` → `Foo` component by stripping the `Props` suffix
2. **File co-location (fallback):** If naming doesn't match, check if a Props interface and a component are defined in the same file
3. **Generic parameter (deep fallback):** Look for `ComponentProps<typeof Foo>` or similar generic patterns that reference the component

For each linked pair, record the association. For unlinked Props interfaces, include them as standalone type exports.

**Step 4 — Extract shared types:**

Extract non-Props type exports using standard AST patterns (same as Forge tier):
- `export type $NAME = $VALUE`
- `export enum $NAME { $$$ }`
- `export interface $NAME { $$$ }` (excluding `*Props` already captured)

### Phase 5: Variant Consolidation

**Skip this phase if `scope.ui_variants` is not specified and no variant directories detected.**

When multiple design system variants exist:

1. **Group components by registry `id`** (NOT by filename — registry is source of truth):
   - For each `id` in `component_catalog[]`, collect all variant paths from `available_in[]` and `code_paths[]`

2. **Select canonical props definition:**
   - Use the primary variant (first in `scope.ui_variants` list) as canonical
   - If primary variant's props are unavailable, use the first available variant

3. **Detect props differences between variants:**
   - For components available in 2+ variants, compare Props interfaces
   - Record any variant-specific props as notes (e.g., "Base UI variant adds `slots` prop")

4. **Deduplicate export counts:**
   - Count unique components (by registry `id`), not total files across variants
   - Record: `components_unique: {N}`, `components_total_with_variants: {M}`

Display: "**Variant consolidation: {unique} unique components across {variant_count} variants** ({total} total including variants). Primary variant: {primary_name}."

### Phase 6: Build Component Extraction Results

Compile all extracted data into the format expected by step-03 section 5:

**Per-export entry (for Props interfaces — primary API):**

- Interface name (e.g., `NativeLiquidButtonProps`)
- Full interface with all fields and types
- Parameters: each field as name, type, required/optional, default
- Linked component name (e.g., `NativeLiquidButton`)
- Source file and line number
- Provenance citation
- Confidence tier (T1 or T1-low)

**Per-export entry (for component functions):**

- Component name
- Linked Props interface (if found)
- Source file and line number
- Provenance citation
- Confidence tier

**Per-export entry (for shared types):**

- Same as standard extraction format

**Component library aggregate counts:**

- `components_registered`: count from registry (or 0)
- `components_documented`: count of components with linked Props
- `props_interfaces_extracted`: count of `*Props` interfaces
- `components_unique`: deduplicated count (after variant consolidation)
- `demo_files_excluded`: count from Phase 1
- `design_variants`: map of variant name → component count (if variants exist)

**Store `component_catalog[]` in context** — this is consumed by step-05 for the Component Catalog section.

Display: "**Component extraction complete.** Returning to main extraction flow."

## RETURN PROTOCOL

After Phase 6 completes, return control to step-03 section 5 (Build Extraction Inventory). The extraction results from this step are merged into the standard extraction inventory format. Step-03 continues with its normal Gate 2 summary and menu.

Do NOT load `{returnToStep}` — the calling step (step-03) will continue from where it delegated.

---

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:

- Demo/example files detected and excluded with user confirmation
- Registry detected (or user provided path) and parsed into component_catalog
- Props interfaces extracted as primary API contracts
- Components linked to Props via 3-level fallback chain
- Variant consolidation produced deduplicated counts (if applicable)
- All extracted items have provenance citations
- Results compatible with step-03 section 5 inventory format
- component_catalog stored in context for step-05

### FAILURE:

- Excluding demo files without user confirmation
- Accepting a registry candidate without user confirmation
- Not extracting Props interfaces as primary API surface
- Documenting component function signatures instead of Props
- Including hallucinated component data not in source
- Variant deduplication based on filenames instead of registry IDs
- Not returning control to step-03 after completion

**Master Rule:** Zero hallucination — every extraction must trace to source code. The component registry is the source of truth for the API surface.
