---
nextStepFile: 'summary.md'
---

<!-- Config: communicate in {communication_language}. Render the token report in {document_output_language}. -->

# Step 5: Token Report

## STEP GOAL:

To calculate approximate token counts for all exported artifacts and present a clear report showing the token cost of each component, helping users understand the context budget impact of their skills.

## Rules

- Focus only on token counting and reporting — read-only measurement
- Auto-proceed when complete
- **Multi-skill mode:** when step 1 loaded more than one skill (`len(skill_batch) > 1`), compute token counts per skill, then present one aggregate table with one row per skill (context-snippet.md, SKILL.md, metadata.json, references/, package total). Measure the managed section once for the run — it is shared across the batch. See step 1 §1c.

## MANDATORY SEQUENCE

### 1. Calculate Token Counts

For each artifact, estimate tokens using the heuristic: **words * 1.3** (approximate for GPT/Claude tokenizers). This same heuristic is used in step 3 for snippet token estimation.

**Artifacts to measure:**

1. **context-snippet.md** — The compressed snippet (if generated)
2. **Managed section** — The complete `<!-- SKF:BEGIN/END -->` block (all skills, not just this one)
3. **SKILL.md** — The full active skill document
4. **metadata.json** — The machine-readable metadata
5. **references/** — Total across all reference files (if present)
6. **Full package total** — Sum of this skill's own artifacts (context-snippet.md + SKILL.md + metadata.json + references/). **Exclude the Managed section row (item 2)** — it is a shared all-skills cost (it bundles this skill's snippet plus every other skill's snippet), reported separately under Context Budget Impact. Including it would double-count this skill's snippet and fold in unrelated skills' costs.

**If passive_context was disabled:** Skip context-snippet.md and managed section measurements, note as "N/A (disabled)".

### 2. Present Token Report

"**Token Report**

| Artifact | Words | Est. Tokens | Notes |
|----------|-------|-------------|-------|
| context-snippet.md | {n} | ~{t} | Passive context (always-on) |
| Managed section (all skills) | {n} | ~{t} | In {target-file-list}, all {count} skills |
| SKILL.md | {n} | ~{t} | Active skill (on-trigger) |
| metadata.json | {n} | ~{t} | Machine-readable |
| references/ | {n} | ~{t} | {count} files |
| **Package total** | **{n}** | **~{t}** | **This skill's own artifacts (snippet + SKILL.md + metadata + references); excludes the shared Managed section row** |

**Context Budget Impact:**
- **Always-on cost:** ~{managed-section-tokens} tokens (managed section in {target-file-list})
- **On-trigger cost:** ~{skill-tokens} tokens (when SKILL.md is loaded)
- **Full disclosure cost:** ~{total-tokens} tokens (if references/ also loaded)

**Benchmark:** Target is ~80-120 tokens per skill in managed section. Current: ~{snippet-tokens} tokens."

### 3. Proceed to Summary

Display: "**Proceeding to export summary...**"

#### Menu Handling Logic:

- After token report is displayed, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed step with no user choices
- Proceed directly to next step after reporting

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the token report is displayed will you load and read fully `{nextStepFile}` to execute the export summary.

