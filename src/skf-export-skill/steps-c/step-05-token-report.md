---
nextStepFile: './step-06-summary.md'
---

# Step 5: Token Report

## STEP GOAL:

To calculate approximate token counts for all exported artifacts and present a clear report showing the token cost of each component, helping users understand the context budget impact of their skills.

## Rules

- Focus only on token counting and reporting — read-only measurement
- Auto-proceed when complete

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Calculate Token Counts

For each artifact, estimate tokens using the heuristic: **words * 1.3** (approximate for GPT/Claude tokenizers). This same heuristic is used in step-03 for snippet token estimation.

**Artifacts to measure:**

1. **context-snippet.md** — The compressed snippet (if generated)
2. **Managed section** — The complete `<!-- SKF:BEGIN/END -->` block (all skills, not just this one)
3. **SKILL.md** — The full active skill document
4. **metadata.json** — The machine-readable metadata
5. **references/** — Total across all reference files (if present)
6. **Full package total** — Sum of all above

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
| **Package total** | **{n}** | **~{t}** | **All artifacts combined** |

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

