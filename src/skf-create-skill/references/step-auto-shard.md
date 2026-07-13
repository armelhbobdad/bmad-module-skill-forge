---
nextStepFile: 'step-doc-rot.md'
# Resolve `{shardBodyHelper}` by probing `{shardBodyProbeOrder}` in order
# (installed SKF module path first, src/ dev-checkout fallback); first existing
# path wins. HALT if neither resolves — hand line-counting is the least reliable
# deterministic op and would silently ship an over-budget body or wrongly HALT.
shardBodyProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-shard-body.py'
  - '{project-root}/src/shared/scripts/skf-shard-body.py'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5b: Auto-Shard

## STEP GOAL:

Proactively reduce oversized SKILL.md bodies to under 400 lines by extracting Tier 2 sections (`## Full` headings) to `references/`, providing 100 lines of headroom below the 500-line `body.max_lines` ceiling. Tier 1 sections always remain inline. If the body is already within budget, skip cleanly.

## Rules

- Auto-proceed step — no user interaction required
- Graceful skip — if body is under threshold, proceed without modification
- Only extract Tier 2 sections (identified by `## Full` heading prefix)
- Tier 1 sections stay inline — moving one to references/ would break the standalone SKILL.md the two-tier design guarantees
- Do not modify frontmatter — only body content and references/ directory
- Do not invoke `npx skill-check split-body` — this step uses direct extraction
- Do not invoke the Description Guard Protocol — frontmatter is untouched

## MANDATORY SEQUENCE

### §0. Run the Shard Script (primary path)

The counting, boundary detection, size-sort, file writes, and blockquote replacement described in §1–§5 are fully deterministic and run every invocation — so a script owns them, not the model. Do not count body lines or extract sections by hand when the script ran.

**Resolve `{shardBodyHelper}`** from `{shardBodyProbeOrder}`; first existing path wins. HALT if no candidate exists.

Run:

```bash
uv run {shardBodyHelper} <staging-skill-dir>/SKILL.md --budget 400
```

The script performs everything §1–§5 document — it counts the body between the frontmatter close and EOF, enumerates the `## Full` Tier 2 sections, extracts the largest first to `references/` until the body fits, writes the extracted files and the trimmed SKILL.md through the atomic-write helper, rewrites each section as a cross-reference blockquote, and checks Tier 1 preservation and cross-reference integrity. Read its JSON and set context directly:

- **`action: "skip"`** → the body was already within budget. Log `"auto-shard: skipped (body {body_lines_before} lines)"`, set `auto_shard_triggered: false`, `sections_extracted: []`, `body_lines_before`/`body_lines_after` from the report, then skip to §6.
- **`action: "shard"`** → set `auto_shard_triggered: true` and copy `sections_extracted`, `body_lines_before`, `body_lines_after` straight from the report.
- **HALT** if `tier1_preserved` is false: `"Auto-shard removed Tier 1 section(s) {tier1_missing}. Aborting."`
- **HALT** if `xref_ok` is false: `"Auto-shard cross-references did not resolve. Aborting."`
- If `under_budget` is false, selective Tier 2 extraction alone could not bring the body under budget (rare — Tier 1 itself exceeds ~300 lines). Apply the §4 editing-judgment trim, then continue.

Log: `"auto-shard: {N} sections extracted, body reduced from {body_lines_before} to {body_lines_after} lines"`, then proceed to §6.

**Manual fallback (only when `uv`/Python is unavailable):** perform §1–§5 by hand as documented below — they describe exactly what the script does.

### §1. Count Body Lines

The script counts all lines in the staging SKILL.md between the frontmatter closing `---` and EOF, excluding trailing blank lines, and reports the total as `body_lines_before`.

```
body_lines_before = body_line_count
```

**IF `body_line_count` <= 400:** the script emits `action: "skip"` and writes nothing —
- Log: `"auto-shard: skipped (body {body_line_count} lines)"`
- Set context: `auto_shard_triggered: false`, `sections_extracted: []`, `body_lines_before: {body_line_count}`, `body_lines_after: {body_line_count}`
- Skip to §6 (Auto-Proceed)

**ELSE:** the script proceeds to §2.

### §2. Selective Shard — Tier 2 Extraction

The script identifies Tier 2 sections by their `## Full` heading prefix:
- `## Full API Reference` → `references/full-api-reference.md`
- `## Full Type Definitions` → `references/full-type-definitions.md`
- `## Full Integration Patterns` → `references/full-integration-patterns.md`

Sections are sorted by line count descending (largest first).

**FOR EACH Tier 2 section (largest first):**

1. Extract the full section content (from `## Full` heading to the next `##` heading or EOF)
2. Derive the reference filename from the heading: kebab-case (as shown above)
3. Write the extracted content (preserving the `##` heading) to `<staging-skill-dir>/references/{filename}` via the atomic-write helper
4. Replace the extracted section in SKILL.md with a cross-reference blockquote:
   ```markdown
   > See [Full API Reference](references/full-api-reference.md)
   ```
5. Re-count body lines
6. **IF `body_line_count` <= 400:** stop extracting, proceed to §3

The report's `sections_extracted: [{heading, file, lines}]` records exactly which sections were pulled.

### §3. Tier 1 Preservation Check

The script verifies ALL Tier 1 sections that were inline before extraction remain inline in SKILL.md afterward. These headings:

- `## Overview`
- `## Quick Start`
- `## Common Workflows`
- `## Key API Summary` (or `## Component Catalog` for component-library scope)
- `## Migration & Deprecation Warnings` (conditional — only checked if it was present before extraction)
- `## Key Types`
- `## Architecture at a Glance`
- `## CLI` (conditional — only checked if present before extraction)
- `## Scripts & Assets` (conditional — only checked if present before extraction)
- `## Manual Sections` (conditional — only checked if present before extraction)

The result surfaces as `tier1_preserved` (with any pulled headings in `tier1_missing`).

**IF `tier1_preserved` is false:**
HALT: `"Auto-shard removed Tier 1 section {name}. Aborting."`

### §4. Post-Shard Validation

The report's `body_lines_after` is the recount after all extraction. `under_budget` is true when the body now fits.

**IF `under_budget` is false** (body still > 400 after all Tier 2 sections extracted — this is the one genuine editing-judgment step):
- Trim oversized Tier 1 sections: reduce `## Key API Summary` and `## Architecture at a Glance` content to fit within the 400-line budget
- Do not move any Tier 1 section to references/
- Re-run `{shardBodyHelper}` (or re-count) and update `body_lines_after`

### §5. Cross-Reference Integrity

The script verifies, for each extracted reference file, that the file exists at `<staging-skill-dir>/references/{filename}` and that the cross-reference blockquote in SKILL.md links to it — reported as `xref_ok`. HALT if `xref_ok` is false.

Log: `"auto-shard: {N} sections extracted, body reduced from {body_lines_before} to {body_lines_after} lines"`

Set context:
- `auto_shard_triggered: true`
- `sections_extracted: [{heading names}]`
- `body_lines_before: {before}`
- `body_lines_after: {after}`

### §6. Auto-Proceed

Load, read the entire file, then execute `{nextStepFile}`.
