---
nextStepFile: 'validate.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5b: Auto-Shard

## STEP GOAL:

Proactively reduce oversized SKILL.md bodies to under 400 lines by extracting Tier 2 sections (`## Full` headings) to `references/`, providing 100 lines of headroom below the 500-line `body.max_lines` ceiling. Tier 1 sections always remain inline. If the body is already within budget, skip cleanly.

## Rules

- Auto-proceed step — no user interaction required
- Graceful skip — if body is under threshold, proceed without modification
- Only extract Tier 2 sections (identified by `## Full` heading prefix)
- Tier 1 sections must NEVER be moved to references/
- Do not modify frontmatter — only body content and references/ directory
- Do not invoke `npx skill-check split-body` — this step uses direct extraction
- Do not invoke the Description Guard Protocol — frontmatter is untouched

## MANDATORY SEQUENCE

### §1. Count Body Lines

Count all lines in the staging SKILL.md between the frontmatter closing `---` and EOF. Exclude trailing blank lines from the count. Store as `body_line_count`.

```
body_lines_before = body_line_count
```

**IF `body_line_count` <= 400:**
- Log: `"auto-shard: skipped (body {body_line_count} lines)"`
- Set context: `auto_shard_triggered: false`, `sections_extracted: []`, `body_lines_before: {body_line_count}`, `body_lines_after: {body_line_count}`
- Skip to §6 (Auto-Proceed)

**ELSE:** Proceed to §2.

### §2. Selective Shard — Tier 2 Extraction

Identify Tier 2 sections by their `## Full` heading prefix:
- `## Full API Reference` → `references/full-api-reference.md`
- `## Full Type Definitions` → `references/full-type-definitions.md`
- `## Full Integration Patterns` → `references/full-integration-patterns.md`

Sort identified sections by line count descending (extract largest first).

**FOR EACH Tier 2 section (largest first):**

1. Extract the full section content (from `## Full` heading to the next `##` heading or EOF)
2. Derive the reference filename from the heading: kebab-case (as shown above)
3. Write the extracted content (preserving the `##` heading) to `<staging-skill-dir>/references/{filename}`
4. Replace the extracted section in SKILL.md with a cross-reference blockquote:
   ```markdown
   > See [Full API Reference](references/full-api-reference.md)
   ```
5. Re-count body lines
6. **IF `body_line_count` <= 400:** stop extracting, proceed to §3

Track: `sections_extracted: [{heading names}]`

### §3. Tier 1 Preservation Check

Verify ALL Tier 1 sections remain inline in SKILL.md after extraction. Check for these headings:

- `## Overview`
- `## Quick Start`
- `## Common Workflows`
- `## Key API Summary` (or `## Component Catalog` for component-library scope)
- `## Migration & Deprecation Warnings` (conditional — only check if it was present before extraction)
- `## Key Types`
- `## Architecture at a Glance`
- `## CLI` (conditional — only check if present before extraction)
- `## Scripts & Assets` (conditional — only check if present before extraction)
- `## Manual Sections` (conditional — only check if present before extraction)

**IF any Tier 1 section is missing after extraction:**
HALT: `"Auto-shard removed Tier 1 section {name}. Aborting."`

### §4. Post-Shard Validation

Re-count body lines after all Tier 2 sections have been extracted.

```
body_lines_after = body_line_count
```

**IF `body_line_count` > 400 after all Tier 2 sections extracted:**
- Trim oversized Tier 1 sections: reduce `## Key API Summary` and `## Architecture at a Glance` content to fit within the 400-line budget
- Do NOT move any Tier 1 section to references/
- Re-count and update `body_lines_after`

### §5. Cross-Reference Integrity

**FOR EACH extracted reference file:**
1. Verify the file exists at `<staging-skill-dir>/references/{filename}`
2. Verify the cross-reference blockquote in SKILL.md contains a link resolving to the file

Log: `"auto-shard: {N} sections extracted, body reduced from {body_lines_before} to {body_lines_after} lines"`

Set context:
- `auto_shard_triggered: true`
- `sections_extracted: [{heading names}]`
- `body_lines_before: {before}`
- `body_lines_after: {after}`

### §6. Auto-Proceed

Load, read the entire file, then execute `{nextStepFile}`.
