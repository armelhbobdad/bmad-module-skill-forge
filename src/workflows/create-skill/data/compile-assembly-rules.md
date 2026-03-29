# SKILL.md Compilation Assembly Rules

## Frontmatter (REQUIRED — agentskills.io compliance)

```yaml
---
name: {brief.name}
description: >
  {Trigger-optimized description from brief and extraction data.
  Include what it does, when to use it, and what NOT to use it for.
  1-1024 chars, optimized for agent discovery.}
---
```

**Frontmatter rules:**

- `name`: lowercase alphanumeric + hyphens only, must match the skill output directory name. Prefer gerund form (`processing-pdfs`, `analyzing-spreadsheets`) for clarity.
- `description`: non-empty, max 1024 chars, optimized for agent discovery. **MUST use third-person voice** ("Processes Excel files..." not "I can help you..." or "You can use this to..."). Inconsistent point-of-view causes discovery problems since the description is injected into the system prompt.
- Only `name` and `description` in frontmatter — `version` and `author` go in metadata.json
- No other frontmatter fields for standard skills (only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted by spec)

## Two-Tier Assembly

**CRITICAL: Two-tier assembly.** SKILL.md must retain actionable inline content that survives `split-body` extraction. Assemble Tier 1 sections first (always inline), then Tier 2 sections (reference-eligible, may be extracted by split-body).

### Tier 1 — Always Inline (must survive split-body)

These sections form the essential standalone body. Target: **under 300 lines total** for Tier 1. An agent loading only SKILL.md (without references) must get enough to act.

**Section 1 — Overview (~10 lines):**
- 1-line summary of what the library does
- Source repo, version, branch
- Forge tier used for compilation
- Export count and confidence summary

**Section 2 — Quick Start (~30 lines):**
- Select the 3-5 most commonly used functions (by import frequency or documentation prominence)
- One runnable code example showing a typical end-to-end flow (e.g., `add → process → search`)
- Minimal usage examples — ONLY from source tests or official docs
- If no examples exist in source, show signature-only quick start
- Provenance citation for each function

**Section 3 — Common Workflows (~30 lines):**
- 4-5 patterns showing typical function call sequences
- Each pattern: 1-line bold description + function call chain with key params
- Focus on the most common developer tasks, not exhaustive coverage
- Format example:
  ```
  **Add and process data:**
  `await cognee.add(data) → await cognee.cognify() → await cognee.search(query)`
  ```

**Section 4 — Key API Summary (~20 lines):**
- Table of top 10-15 functions: name, purpose, key parameters
- One row per function — no full signatures, just enough for discovery
- Provenance citation per function

**Section 4b — Migration & Deprecation Warnings (~10 lines, Deep tier only):**
- Only populated when step-04 enrichment produced **T2-future** annotations (deprecation warnings, breaking changes, planned renames)
- List each warning as a single-line bullet: function name, what changed or will change, source citation
- Max 10 lines — just the actionable warnings, not full context
- Link to Tier 2 Full API Reference for details: "See Full API Reference for migration details."
- **Skip entirely** for Quick/Forge tiers or when no T2-future annotations exist — do not emit an empty section
- This section survives split-body, ensuring agents always see critical migration context

**Section 5 — Key Types (~20 lines):**
- Most important enum/type definitions inline (e.g., SearchType values, config options)
- Only types that appear in Quick Start or Common Workflows
- Full type details go in Tier 2

**Section 6 — Architecture at a Glance (~10 lines):**
- Bullet list of major subsystem categories (e.g., "Graph DBs: Neo4j, Kuzu, Neptune")
- Adapter/driver overview — what's available, not how it works
- Skip for Quick tier or small libraries with < 5 modules

**Section 7 — CLI (~10 lines, if applicable):**
- Basic CLI commands if the library has a CLI interface
- Skip if no CLI exists

**Section 7b — Scripts & Assets (~10 lines, if applicable):**
- Manifest table of included scripts with filename, one-line purpose, and provenance citation
- Manifest table of included assets with filename, one-line purpose, and provenance citation
- Each entry: `scripts/{filename}` or `assets/{filename}`, purpose, `[SRC:{source_path}:L1]`
- Include a note: "Load scripts from `scripts/` and assets from `assets/` when directed by the instructions above."
- **Skip entirely** when no scripts or assets detected in extraction inventory — do not emit an empty section
- Like Sections 4b and 7, parsers must treat this section as optional

**Section 8 — Manual Sections:**
- Seed empty `<!-- [MANUAL] -->` markers:
```markdown
<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->
```
- Place after Quick Start and after Key API Summary sections

### Tier 2 — Reference-Eligible (can be extracted by split-body)

Assemble Sections 9-11 (Full API Reference, Full Type Definitions, Full Integration Patterns) as defined in the skill-sections data file. These contain full detail and are split into `references/` when the body exceeds 500 lines. Include T2 annotations from enrichment in the Full API Reference (Deep tier only).

**CRITICAL — Tier 2 differentiation from Tier 1:** Tier 2 Full API Reference must contain content that is NOT present in Tier 1's Key API Summary. Specifically:

- **Full parameter tables** with types, defaults, and required/optional flags (Tier 1 only lists key params)
- **Return value details** including structure, types, and error conditions
- **T2 temporal annotations** — migration notes, deprecation details, breaking change context (Deep tier)
- **Usage examples** from source tests or documentation (Tier 1 has signature-only references)
- **Edge cases and constraints** — parameter validation rules, size limits, behavioral notes

Do NOT repeat Tier 1's name/purpose/key-params table format in Tier 2. Tier 2 is a deep reference, not a reformatted summary. This distinction prevents conciseness scorers from flagging the two-tier design as redundancy.

### Component Library Assembly Overrides

When `scope.type: "component-library"` in the brief AND `component_catalog[]` is available in context, apply these overrides to the standard assembly. All other sections remain unchanged.

**Section 2 (Quick Start) — CLI-first override:**

Replace the standard function-based Quick Start with CLI installation:

```markdown
## Quick Start

Install a component:
`npx {cli-name} add {top-component-id}`

{If provider wrapping detected in source:}
Set up providers:
\`\`\`tsx
import { ThemeProvider, UILibraryProvider } from "{primary-package}";

<ThemeProvider>
  <UILibraryProvider>
    <YourApp />
  </UILibraryProvider>
</ThemeProvider>
\`\`\`
```

Detect CLI name from: `package.json` `bin` field, README usage examples, or `registry_path` context. If no CLI detected, fall back to standard import-based Quick Start.

**Section 4 (Key API Summary) — Component Catalog override:**

Replace the function table with a Component Catalog organized by category:

```markdown
## Component Catalog

| Category | Count | Key Components |
|----------|-------|---------------|
| {category} | {count} | {top 3-5 component names, comma-separated} |

**Design system variants:** {variant list with primary marked}
**Total components:** {unique count} | {Per variant: **With {name}:** {count}}
```

Source: `component_catalog[]` from step-03d. Group by `category` field. Provenance: cite the registry file.

**Section 5 (Key Types) — Props-focused override:**

Replace generic types with the top 5 most-used Props interfaces (by component count or prominence):

```markdown
## Key Types

### {ComponentName}Props
| Prop | Type | Default | Required |
|------|------|---------|----------|
| {prop} | {type} | {default or —} | {yes/no} |
```

Show only the 5 most important Props interfaces inline. Full Props details go in Tier 2.

**Tier 2 (Full API Reference) — Props Reference override:**

Organize by component (not by function). Per component:

```markdown
### {ComponentName}

**Install:** `npx {cli} add {component-id}`
**Available in:** {variant list}
**Props:** `{ComponentName}Props`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| {prop} | {type} | {default} | {JSDoc description or —} |
```

**context-snippet.md — Component Library format:**

```markdown
[{name} v{version}]|root: skills/{name}/
|IMPORTANT: {name} v{version} — read SKILL.md before writing {name} code. Do NOT rely on training data.
|install: npx {cli} add <component-id>
|catalog:{SKILL.md#component-catalog} — {N} components: {category(count), ...}
|variants: {variant list} — {provider wrapping note if applicable}
|key-props:{SKILL.md#key-types} — {top props interfaces with key fields}
|gotchas: {detected gotchas}
```

**metadata.json — Component Library stats:**

When `scope.type: "component-library"`, add these fields to `stats`:

```json
{
  "stats": {
    "components_registered": 0,
    "components_documented": 0,
    "props_interfaces_extracted": 0,
    "components_unique": 0,
    "demo_files_excluded": 0,
    "design_variants": {}
  }
}
```

These are in addition to the standard stats fields (exports_documented, etc.).

### Assembly Rules

1. Assemble all Tier 1 sections first — these form the essential standalone body
2. Assemble all Tier 2 sections after — these are progressive disclosure detail
3. Tier 1 content MUST be under 300 lines (excluding frontmatter)
4. If Tier 1 alone exceeds 300 lines, reduce Key API Summary and Architecture at a Glance
5. Tier 1 sections are kept short enough that `split-body` targets the larger Tier 2 sections (`## Full ...` headings) instead
6. After split-body, SKILL.md must still contain all Tier 1 sections with actionable content
7. **Signature fidelity:** When populating function entries from the extraction inventory, always use the `params` and `return_type` fields from the provenance-map entry (T1/AST-backed). Do not substitute parameter names, types, or return types from documentation, README examples, or enrichment annotations. T2/T3 sources may enrich descriptions and add usage notes, but structural signature data from AST extraction is authoritative.

### Reference File Rules

- **Table of contents required** for any reference file exceeding 100 lines — include a `## Contents` section at the top listing all sub-sections. This ensures agents can see the full scope even when previewing with partial reads.
- One file per major function group or type — group by module, file, or functional area
- Name files descriptively: `form_validation_rules.md`, not `doc2.md`

### Content Quality Rules

These rules apply to all content assembled in SKILL.md and reference files.

**Degrees of freedom:** Match instruction specificity to the task's fragility and variability:
- **High freedom** (text guidance): When multiple approaches are valid and context determines the best one. Example: code review patterns, architecture suggestions.
- **Medium freedom** (pseudocode/parameterized scripts): When a preferred pattern exists but variation is acceptable. Example: configuration templates, report generation.
- **Low freedom** (exact scripts, no parameters): When operations are fragile and consistency is critical. Example: database migrations, deployment sequences. Use "Run exactly this" language.

**Consistent terminology:** Choose one term per concept and use it throughout the skill. Do not mix synonyms (e.g., "API endpoint" vs "URL" vs "route", or "field" vs "box" vs "element"). Consistency helps agents understand and follow instructions deterministically.

**Avoid time-sensitive information:** Do not include date-conditional instructions ("If before August 2025, use the old API"). Instead, document the current method and place deprecated patterns in a collapsible "Old patterns" section with the deprecation date.

**Template and examples patterns:**
- **For strict requirements** (API responses, data formats): Provide an exact template with "ALWAYS use this exact structure" language.
- **For flexible guidance** (reports, analysis): Provide a sensible default template with "Adjust sections as needed" language.
- **Input/output examples:** When output quality depends on seeing examples and concrete pairs exist in source tests or official docs, include 2-3 input/output pairs sourced from those tests or docs. Examples help agents understand desired style and detail more clearly than descriptions alone. If no examples exist in source, note the gap rather than fabricating pairs — zero hallucination applies.

**Workflow checklist pattern:** When a skill includes multi-step workflows, provide a copy-paste checklist that agents can track progress against:
```markdown
Copy this checklist and track your progress:
- [ ] Step 1: {action}
- [ ] Step 2: {action}
```

**Verifiable intermediate outputs:** For skills involving batch operations, destructive changes, or complex validation, recommend the plan-validate-execute pattern: create a structured plan file (e.g., `changes.json`), validate it with a script, then execute. This catches errors before changes are applied.
