# Component Library Assembly Overrides

When `scope.type: "component-library"` in the brief AND `component_catalog[]` is available in context, apply these overrides to the standard assembly of `assets/compile-assembly-rules.md`. All other sections remain unchanged.

**Section 2 (Quick Start), CLI-first override:**

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

**Section 4 (Key API Summary), Component Catalog override:**

Replace the function table with a Component Catalog organized by category:

```markdown
## Component Catalog

| Category | Count | Key Components |
|----------|-------|---------------|
| {category} | {count} | {top 3-5 component names, comma-separated} |

**Design system variants:** {variant list with primary marked}
**Total components:** {unique count} | {Per variant: **With {name}:** {count}}
```

Source: `component_catalog[]` from step 3d. Group by `category` field. Provenance: cite the registry file.

**Section 5 (Key Types), Props-focused override:**

Replace generic types with the top 5 most-used Props interfaces (by component count or prominence):

```markdown
## Key Types

### {ComponentName}Props
| Prop | Type | Default | Required |
|------|------|---------|----------|
| {prop} | {type} | {default, or an em dash} | {yes/no} |
```

Show only the 5 most important Props interfaces inline. Full Props details go in Tier 2.

**Tier 2 (Full API Reference), Props Reference override:**

Organize by component (not by function). Per component:

```markdown
### {ComponentName}

**Install:** `npx {cli} add {component-id}`
**Available in:** {variant list}
**Props:** `{ComponentName}Props`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| {prop} | {type} | {default} | {JSDoc description, or an em dash} |
```

**context-snippet.md, Component Library format:**

```markdown
[{name} v{version}]|root: skills/{name}/
|IMPORTANT: {name} v{version} — read SKILL.md before writing {name} code. Do NOT rely on training data.
|install: npx {cli} add <component-id>
|catalog:{SKILL.md#component-catalog} — {N} components: {category(count), ...}
|variants: {variant list} — {provider wrapping note if applicable}
|key-props:{SKILL.md#key-types} — {top props interfaces with key fields}
|gotchas: {detected gotchas}
```

**metadata.json, Component Library stats:**

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
