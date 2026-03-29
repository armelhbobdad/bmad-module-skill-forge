---
name: 'step-05-compile'
description: 'Assemble SKILL.md, context-snippet, metadata, and references from extraction inventory'
nextStepFile: './step-06-validate.md'
skillSectionsData: '../data/skill-sections.md'
assemblyRulesData: '../data/compile-assembly-rules.md'
---

# Step 5: Compile

## STEP GOAL:

To assemble the complete skill content from the extraction inventory and enrichment annotations — building SKILL.md sections, context-snippet.md, metadata.json, and references/ content according to the agentskills.io format.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 ALWAYS follow the exact instructions in the step file
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill compilation engine performing structured assembly
- ✅ Every instruction in SKILL.md must trace to source code with a provenance citation
- ✅ Uncitable content is excluded, not guessed — zero hallucination

### Step-Specific Rules:

- 🎯 Focus ONLY on assembling content from extraction inventory + enrichment
- 🚫 FORBIDDEN to include any content without a provenance citation
- 💾 Sub-agents and compilation processes may write to a staging directory (e.g., `_bmad-output/{name}/`)
- 🚫 FORBIDDEN to write final files to `skills/` or `forge-data/` — that's step-07
- 🚫 FORBIDDEN to fabricate examples not found in source tests or docs
- ⚒️ Seed `<!-- [MANUAL] -->` markers for future update-skill compatibility

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Build all content in context AND write to the staging directory (`_bmad-output/{name}/`) — staging write is mandatory for step-06 validation
- 📖 Follow agentskills.io section structure from data file
- 🚫 Do not promote any output files to final `skills/` or `forge-data/` directories — that's step-07

## CONTEXT BOUNDARIES:

- Available: extraction_inventory, enrichment_annotations (if Deep), doc_fetch_inventory (if doc_urls), brief_data, tier
- Focus: Assembling structured content from verified data
- Docs-only mode: If `source_type: "docs-only"`, all content is T3 `[EXT:{url}]`. Overview must note "Generated from external documentation." metadata.json `source_authority` forced to `community`. No AST/source citations exist — only `[EXT:...]` citations.
- Limits: Do NOT write to final `skills/` or `forge-data/` directories, validate spec compliance, or report
- Dependencies: Extraction inventory from step-03 (enrichment from step-04 if Deep)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Data Files

Load `{skillSectionsData}` and `{assemblyRulesData}` completely. These define the agentskills.io-compliant format and detailed assembly rules for all output artifacts.

### 1b. Signature Fidelity Rule

**When assembling function signatures, parameter lists, and return types in any SKILL.md section or reference file:**

- **T1 provenance-map entries (AST-extracted) are authoritative** for: function name, parameter names, parameter types, parameter order, return type, and optionality markers (e.g., `?`, `Optional`, `= default`).
- **T2 (QMD-enriched) and T3 (doc-derived) sources may ADD** contextual descriptions, usage notes, behavioral documentation, and examples to function entries, but **MUST NOT REPLACE** structural signature data from T1 entries.
- **On conflict:** If a T2/T3 source provides a different signature than the T1 extraction for the same export (e.g., different parameter count, different types, missing `Partial<>` wrapper), keep the T1 signature and log a warning in the evidence report: "Signature conflict for `{export_name}`: T1 shows `{t1_signature}`, T2/T3 shows `{other_signature}`. T1 used as authoritative."
- **`signature_source` field:** Record `signature_source: "T1" | "T1-low" | "T2" | "T3"` in each provenance-map entry to indicate the highest-confidence tier that contributed the structural signature data (params, return_type). This enables test-skill to verify signature provenance.

This rule applies to ALL sections including Tier 1 Key API Summary, Tier 2 Full API Reference, and Section 4b Migration & Deprecation Warnings.

### 2. Build SKILL.md Content

Assemble each section in order using the assembly rules data file (`{assemblyRulesData}`). The data file specifies frontmatter format, Tier 1 section details (Sections 1-8, including conditional Section 7b for scripts/assets), Tier 2 section details (Sections 9-11), and assembly ordering rules. Follow it exactly. Assemble Section 7b (Scripts & Assets) only if `scripts_inventory` or `assets_inventory` is non-empty.

### 3. Build context-snippet.md Content

Vercel-aligned indexed format for CLAUDE.md managed section (~80-120 tokens):

```markdown
[{skill-name} v{version}]|root: skills/{skill-name}/
|IMPORTANT: {skill-name} v{version} — read SKILL.md before writing {skill-name} code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start}
|api: {top exports with () for functions, comma-separated}
|key-types:{SKILL.md#key-types} — {inline summary of most important type values}
|gotchas: {2-3 most critical pitfalls or breaking changes, inline}
```

**Derivation rules:**

- **version**: From source detection (reconciled in step-03), not brief default
- **api**: Top 10 exports from extraction inventory, append `()` to function names
- **key-types**: Inline summary of most important enum/type values from Key Types section
- **gotchas**: Derived from T2-future annotations (breaking changes), async requirements, version-specific behavior changes. If no gotchas available, omit the gotchas line.
- **Section anchors** (`#quick-start`, `#key-types`): Must match actual heading slugs in the assembled SKILL.md

### 4. Build metadata.json Content

Following the structure from the skill-sections data file:
- Populate all fields from brief_data, extraction inventory, and tier
- Set `generation_date` to current ISO-8601 timestamp
- Set `source_commit` from resolved source (if available)
- Set `stats` from extraction aggregate counts:
  - `exports_documented`: count of exports with documentation in the assembled SKILL.md
  - `exports_public_api`: count of exports from public entry points (`__init__.py`, `index.ts`, `lib.rs`, or equivalent) — derive this from step-03's entry-point validation (section 4b), NOT from the provenance-map entry count (which may be incomplete if extraction patterns missed some export types)
  - `exports_internal`: count of all other non-underscore-prefixed exports (internal modules, helpers, adapters)
  - `exports_total`: `exports_public_api` + `exports_internal`
  - `public_api_coverage`: `exports_documented / exports_public_api` (1.0 when all public API exports are documented; `null` if `exports_public_api` is 0)
  - `total_coverage`: `exports_documented / exports_total` (may be low for large codebases — this is expected; `null` if `exports_total` is 0)
- Set `description` from the SKILL.md frontmatter `description` field (already assembled in section 2)
- Set `language` from source analysis (e.g., `"typescript"`, `"python"`) — use the primary language of the entry point file
- Set `ast_node_count` from extraction stats if ast-grep was used (Forge/Deep tier), otherwise omit
- Set `tool_versions` based on tier and available tools. Resolve `{skf_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `{project-root}/_bmad/skf/package.json` → read `.version` field
  2. `node -p "require('./node_modules/bmad-module-skill-forge/package.json').version"`
  3. `{project-root}/_bmad/skf/VERSION` → read plain text file (single line containing version string, written by the SKF installer)
  4. `"unknown"` (final fallback — add a warning to the evidence report)
  Never hardcode the version.
- Resolve `{ast_grep_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `ast-grep --version` → parse version string from output (e.g., `ast-grep 0.41.1` → `"0.41.1"`)
  2. `mcp__ast-grep__find_code` tool metadata (if version is exposed by the MCP server)
  3. `"unknown"` (final fallback — add a warning to the evidence report)
- Resolve `{qmd_version}` using this resolution chain (try each in order, use the first that succeeds):
  1. `qmd --version` → parse version string from output (e.g., `qmd 2.0.1` → `"2.0.1"`)
  2. `mcp__plugin_qmd-plugin_qmd__status` → parse version if exposed in status output
  3. `"unknown"` (final fallback — add a warning to the evidence report)
  Note: QMD is a Bun/Node package (`@tobilu/qmd`). Install via `bun install -g @tobilu/qmd`.
- Store `commit_short` = first 8 characters of `source_commit` (or `"unknown"` if unavailable) for use in step-08 report.
- If `scripts_inventory` is non-empty, populate `scripts[]` array and set `stats.scripts_count`. If `assets_inventory` is non-empty, populate `assets[]` array and set `stats.assets_count`. Omit these fields entirely when inventories are empty.

### 5. Build references/ Content

Create one reference file per major function group or type:
- Full function signatures with detailed parameter descriptions
- Complete usage examples (from source only)
- Related functions cross-references
- Temporal annotations (Deep tier: T2-past, T2-future)

Group functions logically by module, file, or functional area.

### 6. Build provenance-map.json Content

One entry per extracted export: export_name, export_type, params[] (typed strings), return_type, source_file, source_line, confidence tier (T1/T1-low/T2), extraction_method, ast_node_type, signature_source ("T1"|"T1-low"|"T2"|"T3" — indicates which tier contributed the structural signature). If `scripts_inventory` or `assets_inventory` is non-empty, add `file_entries[]` with file_name, file_type, source_file, content_hash, confidence, extraction_method. See `{skillSectionsData}` for full schema.

### 7. Build evidence-report.md Content

Compilation audit trail: generation date, forge tier, source info, tool versions, extraction summary (files/exports/confidence), warnings. For validation-specific fields (Schema, Body, Security, Content Quality, tessl, Metadata), insert the placeholder text `[PENDING — populated by step-06]`. Step-06 will replace these placeholders with actual results. See `{skillSectionsData}` for full template. Use the same `{skf_version}` value resolved in section 4 when populating the Tool Versions block.

### 8. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After all content is assembled in context (or written to the staging directory), immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed assembly step with no user choices
- All content stays in context or in the staging directory — no final files are written yet
- Proceed directly to validation after assembly is complete

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all 6 content artifacts (SKILL.md, context-snippet.md, metadata.json, references/, provenance-map.json, evidence-report.md) are assembled in context will you proceed to load `{nextStepFile}` for spec validation. Note: extraction-rules.yaml is generated by step-07 from extraction data, not assembled here.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Skill-sections data file and assembly rules data file loaded and followed
- SKILL.md assembled with all required sections in agentskills.io format
- Tier 1 sections assembled first and kept under 300 lines (excluding frontmatter)
- Tier 2 sections assembled after all Tier 1 sections
- Section 4b emitted only when Deep tier AND T2-future annotations exist; omitted entirely otherwise (no empty section)
- Every function entry has a provenance citation
- [MANUAL] markers seeded for update-skill compatibility
- context-snippet.md, metadata.json, references/, provenance-map.json, evidence-report.md all assembled
- No content without provenance citations included
- Auto-proceeded to step-06

### ❌ SYSTEM FAILURE:

- Including functions or examples without provenance citations
- Fabricating usage examples not found in source
- Writing files to final `skills/` or `forge-data/` directories (that's step-07)
- Missing required SKILL.md sections
- Emitting an empty Section 4b when no T2-future annotations exist
- Tier 1 content exceeding 300 lines without reduction
- Assembling Tier 2 sections before Tier 1 sections
- Not seeding [MANUAL] markers
- Not building all 6 content artifacts (extraction-rules.yaml is built by step-07)

**Master Rule:** Zero hallucination — every line of SKILL.md must trace to source code. Compile from data, not imagination.
