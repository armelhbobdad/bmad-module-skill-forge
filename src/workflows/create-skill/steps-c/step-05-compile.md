---
name: 'step-05-compile'
description: 'Assemble SKILL.md, context-snippet, metadata, and references from extraction inventory'
nextStepFile: './step-06-validate.md'
skillSectionsData: '../data/skill-sections.md'
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
- 🚫 FORBIDDEN to write files — content stays in context until step-07
- 🚫 FORBIDDEN to fabricate examples not found in source tests or docs
- ⚒️ Seed `<!-- [MANUAL] -->` markers for future update-skill compatibility

## EXECUTION PROTOCOLS:

- 🎯 Follow MANDATORY SEQUENCE exactly
- 💾 Build all content in context — do not write files
- 📖 Follow agentskills.io section structure from data file
- 🚫 Do not write any output files — that's step-07

## CONTEXT BOUNDARIES:

- Available: extraction_inventory, enrichment_annotations (if Deep), brief_data, tier
- Focus: Assembling structured content from verified data
- Limits: Do NOT write files, validate spec compliance, or report
- Dependencies: Extraction inventory from step-03 (enrichment from step-04 if Deep)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Section Structure

Load `{skillSectionsData}` completely. This defines the agentskills.io-compliant format for all output artifacts.

### 2. Build SKILL.md Content

Assemble each section in order from the skill-sections data file:

**Frontmatter (REQUIRED — agentskills.io compliance):**

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

- `name`: lowercase alphanumeric + hyphens only, must match the skill output directory name
- `description`: non-empty, max 1024 chars, optimized for agent discovery
- Only `name` and `description` in frontmatter — `version` and `author` go in metadata.json
- No other frontmatter fields for standard skills (only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted by spec)

**Section 1 — Overview:**
- What this skill provides
- Source repo, version, branch
- Forge tier used for compilation
- Export count and confidence summary

**Section 2 — Quick Start:**
- Select the 3-5 most commonly used functions (by import frequency or documentation prominence)
- Minimal usage examples — ONLY from source tests or official docs
- If no examples exist in source, show signature-only quick start
- Provenance citation for each function

**Section 3 — API Reference:**
- Group by module/file
- For each exported function:
  - Full signature with types
  - Parameters table (name, type, required/optional, description)
  - Return type
  - Usage example (from source tests/docs ONLY — omit if none found)
  - Provenance citation: `[AST:{file}:L{line}]` or `[SRC:{file}:L{line}]`
  - T2 annotations (Deep tier only): temporal context from enrichment

**Section 4 — Type Definitions:**
- All exported types, interfaces, enums
- Full type signatures with provenance citations

**Section 5 — Integration Patterns (Forge/Deep only):**
- Co-import patterns detected by ast_bridge
- Common usage combinations
- Skip for Quick tier (no co-import data available)

**Section 6 — Manual Sections:**
- Seed empty `<!-- [MANUAL] -->` markers:
```markdown
<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->
```
- Place after Quick Start and after API Reference sections

### 3. Build context-snippet.md Content

Compressed 2-line format for CLAUDE.md managed section:

```markdown
{skill-name} -> skills/{skill-name}/
  exports: {comma-separated top 10 function names}
```

### 4. Build metadata.json Content

Following the structure from the skill-sections data file:
- Populate all fields from brief_data, extraction inventory, and tier
- Set `generated_at` to current ISO-8601 timestamp
- Set `source_commit` from resolved source (if available)
- Set `stats` from extraction aggregate counts
- Set `tool_versions` based on tier and available tools

### 5. Build references/ Content

Create one reference file per major function group or type:
- Full function signatures with detailed parameter descriptions
- Complete usage examples (from source only)
- Related functions cross-references
- Temporal annotations (Deep tier: T2-past, T2-future)

Group functions logically by module, file, or functional area.

### 6. Build provenance-map.json Content

One entry per extracted claim:
- claim text
- source_file and source_line
- confidence tier (T1, T1-low, T2)
- extraction_method (ast_bridge.scan_definitions, gh_bridge.read_file, qmd_bridge.search)
- ast_node_type (if AST-extracted)

### 7. Build evidence-report.md Content

Compilation audit trail:
- Generation date, forge tier, source info
- Tool versions used
- Extraction summary (files scanned, exports found, confidence breakdown)
- Validation results (populated in step-06)
- Warnings from extraction or enrichment

### 8. Menu Handling Logic

**Auto-proceed step — no user interaction.**

After all content is assembled in context, immediately load, read entire file, then execute `{nextStepFile}`.

#### EXECUTION RULES:

- This is an auto-proceed assembly step with no user choices
- All content stays in context — no files are written yet
- Proceed directly to validation after assembly is complete

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all 7 content artifacts (SKILL.md, context-snippet.md, metadata.json, references/, provenance-map.json, evidence-report.md, extraction-rules.yaml) are assembled in context will you proceed to load `{nextStepFile}` for spec validation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Skill-sections data file loaded and followed
- SKILL.md assembled with all required sections in agentskills.io format
- Every function entry has a provenance citation
- [MANUAL] markers seeded for update-skill compatibility
- context-snippet.md, metadata.json, references/, provenance-map.json, evidence-report.md all assembled
- No content without provenance citations included
- Auto-proceeded to step-06

### ❌ SYSTEM FAILURE:

- Including functions or examples without provenance citations
- Fabricating usage examples not found in source
- Writing files to disk (that's step-07)
- Missing required SKILL.md sections
- Not seeding [MANUAL] markers
- Not building all 7 content artifacts

**Master Rule:** Zero hallucination — every line of SKILL.md must trace to source code. Compile from data, not imagination.
