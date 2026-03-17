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

- `name`: lowercase alphanumeric + hyphens only, must match the skill output directory name
- `description`: non-empty, max 1024 chars, optimized for agent discovery
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

### Assembly Rules

1. Assemble all Tier 1 sections first — these form the essential standalone body
2. Assemble all Tier 2 sections after — these are progressive disclosure detail
3. Tier 1 content MUST be under 300 lines (excluding frontmatter)
4. If Tier 1 alone exceeds 300 lines, reduce Key API Summary and Architecture at a Glance
5. Tier 1 sections are kept short enough that `split-body` targets the larger Tier 2 sections (`## Full ...` headings) instead
6. After split-body, SKILL.md must still contain all Tier 1 sections with actionable content
