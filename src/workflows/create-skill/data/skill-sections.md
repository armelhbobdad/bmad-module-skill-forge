# SKILL.md Section Structure

## agentskills.io Compliant Format

### Frontmatter (Required — agentskills.io Compliance)

```yaml
---
name: {skill-name}
description: >
  {Trigger-optimized description of what the skill does and when to use it.
  Include specific keywords for agent discovery.
  Mention what NOT to use it for if applicable.
  1-1024 characters.}
---
```

**Frontmatter rules (agentskills.io specification):**

- `name`: 1-64 characters, lowercase alphanumeric + hyphens only, must match parent directory name. Prefer gerund form (`processing-pdfs`, `analyzing-spreadsheets`) for clarity; noun phrases and action-oriented forms are acceptable alternatives.
- `description`: 1-1024 characters, trigger-optimized for agent matching. MUST use third-person voice ("Processes..." not "I can..." or "You can...").
- Only 6 fields permitted: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`
- `version` and `author` belong in metadata.json, NOT in frontmatter

### Two-Tier Section Structure

SKILL.md uses a two-tier structure to ensure actionable content survives `split-body` extraction.

#### Tier 1 — Always Inline (survives split-body, target <300 lines)

| # | Section | Budget | Purpose |
|---|---------|--------|---------|
| 1 | **Overview** | ~10 lines | What the library does, source repo, version, tier, export count |
| 2 | **Quick Start** | ~30 lines | 3-5 core functions with one runnable end-to-end example |
| 3 | **Common Workflows** | ~30 lines | 4-5 typical function call sequences for common tasks |
| 4 | **Key API Summary** | ~20 lines | Table of top 10-15 functions (name, purpose, key params) |
| 4b | **Migration & Deprecation Warnings** | ~10 lines | T2-future warnings inline (Deep tier only, skip if none) |
| 5 | **Key Types** | ~20 lines | Most important enum/type values inline |
| 6 | **Architecture at a Glance** | ~10 lines | Bullet list of subsystem categories |
| 7 | **CLI** | ~10 lines | Basic CLI commands (skip if no CLI) |
| 7b | **Scripts & Assets** | ~10 lines | Manifest of included scripts and assets (skip if none detected) |
| 8 | **Manual Sections** | ~5 lines | `<!-- [MANUAL] -->` markers for update-skill |

#### Tier 2 — Reference-Eligible (extracted by split-body into references/)

| # | Section | Purpose |
|---|---------|---------|
| 9 | **Full API Reference** | Complete signatures, parameter tables, return types, examples, citations |
| 10 | **Full Type Definitions** | All types, interfaces, enums with full field details |
| 11 | **Full Integration Patterns** | Co-import patterns, adapter details, pipeline internals (Forge/Deep only) |

#### Assembly Rules

- Tier 1 sections are assembled first — they form the standalone body
- Tier 2 sections are assembled after — they are progressive disclosure detail
- Tier 1 sections are kept short enough that `split-body` targets the larger Tier 2 sections (`## Full` headings) into `references/`
- After split-body, SKILL.md retains all Tier 1 content — actionable without loading references
- An agent loading only SKILL.md (no references) must get enough to act
- **Section 4b (Migration & Deprecation Warnings)** is conditional: only emitted for Deep tier when T2-future annotations exist. Quick/Forge/Forge+ tiers and Deep tiers without T2-future annotations omit it entirely (no empty section). Parsers and validators must treat this section as optional.
- **Section 7b (Scripts & Assets)** is conditional: only emitted when `scripts_inventory` or `assets_inventory` is non-empty. Omitted entirely when no scripts or assets are detected. Parsers and validators must treat this section as optional.

### Component Library Section Overrides

When `scope.type: "component-library"`, these section formats replace their standard counterparts. All other sections (Overview, Common Workflows, Architecture, CLI, Manual Sections, etc.) use the standard format.

#### Section 4 — Component Catalog (replaces Key API Summary)

```markdown
## Component Catalog

| Category | Count | Key Components |
|----------|-------|---------------|
| {category} | {count} | {ComponentA}, {ComponentB}, {ComponentC}, ... |

**Design system variants:** {primary} (primary), {variant2}, {variant3}
**Total components:** {unique_count} | **With {variant1}:** {count1} | **With {variant2}:** {count2}
```

- Source: `component_catalog[]` from step-03d extraction
- Group by `category` field from registry
- Show top 3-5 component names per category
- Cite registry file: `[SRC:{registry_file}:L1]`
- Budget: ~20 lines (same as standard Section 4)

#### Section 5 — Key Props (replaces Key Types)

```markdown
## Key Types

### {ComponentName}Props

| Prop | Type | Default | Required |
|------|------|---------|----------|
| {propName} | {type} | {default or —} | {yes/no} |

{Repeat for top 5 Props interfaces}
```

- Show only the 5 most-used Props interfaces (by component count or documentation prominence)
- Full Props details for all components go in Tier 2 reference
- Budget: ~20 lines (same as standard Section 5)

#### Tier 2 — Props Reference (replaces Full API Reference)

```markdown
## Full API Reference

### {ComponentName}

**Install:** `npx {cli} add {component-id}`
**Available in:** {variant list}
**Props:** `{ComponentName}Props`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| {prop} | {type} | {default} | {description from JSDoc or —} |

**Provenance:** `[AST:{file}:L{line}]`
```

- Organize by component, not by function
- Each component shows: install command, variant availability, full props table
- Include JSDoc descriptions for props when available
- Standard provenance citations apply

#### context-snippet.md — Component Library Format

```markdown
[{name} v{version}]|root: skills/{name}/
|IMPORTANT: {name} v{version} — read SKILL.md before writing {name} code. Do NOT rely on training data.
|install: npx {cli} add <component-id>
|catalog:{SKILL.md#component-catalog} — {N} components: {category(count), ...}
|variants: {variant list} — {provider wrapping note if applicable}
|key-props:{SKILL.md#key-types} — {top props interfaces with key fields}
|gotchas: {detected gotchas}
```

### Provenance Citation Format

| Tier | Format | Example |
|------|--------|---------|
| T1 (AST) | `[AST:{file}:L{line}]` | `[AST:src/auth/index.ts:L42]` |
| T1-low (Source) | `[SRC:{file}:L{line}]` | `[SRC:src/auth/index.ts:L42]` |
| T2 (QMD) | `[QMD:{collection}:{doc}]` | `[QMD:project:CHANGELOG.md]` |
| T3 (External) | `[EXT:{url}]` | `[EXT:docs.example.com/api]` |

### [MANUAL] Section Markers

Seed empty manual sections for future update-skill compatibility:

```markdown
<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->
```

Place after Quick Start and after API Reference sections.

---

## context-snippet.md Format (Vercel-aligned indexed format)

Indexed pipe-delimited format for CLAUDE.md managed section (~80-120 tokens per skill). Aligned with Vercel's research finding that retrieval instructions + indexed file maps + inline gotchas dramatically improve agent performance.

```markdown
[{skill-name} v{version}]|root: skills/{skill-name}/
|IMPORTANT: {skill-name} v{version} — read SKILL.md before writing {skill-name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {top exports with () for functions, comma-separated}
|key-types:{SKILL.md#key-types} — {inline summary of most important type values}
|gotchas: {2-3 most critical pitfalls or breaking changes, inline}
```

### Format rules

- **Line 1:** Skill name + version + root path — version signals training data staleness
- **Line 2 (IMPORTANT):** Retrieval instruction — always present, tells agent to read SKILL.md before acting
- **Lines 3+:** Pipe-delimited index mapping topics to SKILL.md sections (with `#anchor` pointers)
- **Inline content:** Each index line includes a brief inline summary (~10 words) so the agent can decide whether to read the full section
- **gotchas line:** 2-3 most critical pitfalls inline — prevents mistakes without requiring a file read
- **Token budget:** ~80-120 tokens per skill (justified by Vercel's finding that indexed format maintains performance at 80% compression)
- **T1-now content only** — no T2 annotations in the snippet
- **Section anchors** (`#quick-start`, `#key-types`) must match actual SKILL.md heading slugs
- **Version** comes from source detection (per issue #32), not brief default

---

## metadata.json Structure

```json
{
  "name": "{skill-name}",
  "version": "{source-version}",
  "skill_type": "single",
  "source_authority": "{official|community|internal}",
  "source_repo": "{github-url}",
  "source_root": "{resolved-source-path}",
  "source_commit": "{commit-hash}",
  "confidence_tier": "{Quick|Forge|Forge+|Deep}",
  "spec_version": "1.3",
  "generation_date": "{ISO-8601}",
  "description": "{SKILL.md frontmatter description}",
  "language": "{primary-source-language}",
  "ast_node_count": "{number-or-omitted-if-no-ast}",
  "exports": [],
  "tool_versions": {
    "ast_grep": "{version-or-null}",
    "qmd": "{version-or-null}",
    "skf": "{skf_version}"
  },
  "confidence_distribution": {
    "t1": 0,
    "t1_low": 0,
    "t2": 0,
    "t3": 0
  },
  "stats": {
    "exports_documented": 0,
    "exports_public_api": 0,
    "exports_internal": 0,
    "exports_total": 0,
    "public_api_coverage": 0.0,
    "total_coverage": 0.0,
    "scripts_count": 0,
    "assets_count": 0
  },
  // scripts[] and assets[] — include ONLY when inventories are non-empty; omit entirely otherwise
  // "scripts": [{ "file": "scripts/{name}", "purpose": "{description}", "source_file": "{source-path}", "confidence": "T1-low" }],
  // "assets": [{ "file": "assets/{name}", "purpose": "{description}", "source_file": "{source-path}", "confidence": "T1-low" }],
  "generated_by": "{quick-skill|create-skill}",
  "dependencies": [],
  "compatibility": "{semver-range}"
}
```

---

## references/ Directory Structure

One file per major function group or type:

```
references/
├── {function-group-a}.md    — Detailed reference with full examples
├── {function-group-b}.md    — Detailed reference with full examples
└── {type-name}.md           — Type definition details
```

Each reference file includes:
- Full function signatures
- Detailed parameter descriptions
- Return value details
- Complete usage examples
- Related functions cross-references
- Temporal annotations (Deep tier: T2-past, T2-future)
- **Table of contents** (required for files exceeding 100 lines) — a `## Contents` section at the top listing all sub-sections for agent discoverability

---

## provenance-map.json Structure

```json
{
  "skill_name": "{name}",
  "source_repo": "{url}",
  "source_commit": "{hash}",
  "generated_at": "{ISO-8601}",
  "entries": [
    {
      "export_name": "getToken",
      "export_type": "function",
      "params": ["userId: string", "options?: TokenOptions"],
      "return_type": "Token",
      "source_file": "src/auth/index.ts",
      "source_line": 42,
      "confidence": "T1",
      "extraction_method": "ast-grep",
      "ast_node_type": "export_function_declaration",
      "signature_source": "T1"
    }
  ],
  "file_entries": [
    {
      "file_name": "scripts/{name}",
      "file_type": "script",
      "source_file": "{source-path}",
      "confidence": "T1-low",
      "extraction_method": "file-copy",
      "content_hash": "sha256:{hash}"
    }
  ]
}
```

`scripts` and `assets` arrays in metadata.json are optional — omit entirely (not empty arrays) when no scripts/assets exist. `file_entries` in provenance-map.json is optional — omit when no scripts/assets exist.

---

## evidence-report.md Structure

```markdown
# Evidence Report: {skill-name}

**Generated:** {date}
**Forge Tier:** {tier}
**Source:** {repo} @ {commit}

## Tool Versions
- ast-grep: {version}
- QMD: {version}
- SKF: {skf_version}

## Extraction Summary
- Files scanned: {count}
- Exports found: {count}
- Confidence: T1={n}, T1-low={n}, T2={n}, T3={n}

## Validation Results
- Schema: {pass/fail}
- Frontmatter: {pass/fail}

## Warnings
- {any warnings from extraction or validation}
```
