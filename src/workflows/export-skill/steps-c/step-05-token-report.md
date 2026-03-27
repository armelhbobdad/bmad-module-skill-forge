---
name: 'step-05-token-report'
description: 'Calculate and report token counts for all export artifacts'

nextStepFile: './step-06-summary.md'
---

# Step 5: Token Report

## STEP GOAL:

To calculate approximate token counts for all exported artifacts and present a clear report showing the token cost of each component, helping users understand the context budget impact of their skills.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a delivery and packaging specialist in Ferris Delivery mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Report clearly — token counts inform developers' context budget decisions

### Step-Specific Rules:

- 🎯 Focus only on token counting and reporting
- 🚫 FORBIDDEN to modify any files — read-only measurement
- 💬 This is a deterministic reporting step — auto-proceed when complete

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Hold token counts in context for the summary step
- 📖 Use consistent estimation method across all files
- 🚫 No file writes — measurement only

## CONTEXT BOUNDARIES:

- Available: All artifacts from steps 01-04 (SKILL.md, metadata.json, context-snippet.md, managed section content)
- Focus: Token estimation and reporting
- Limits: Estimates only — exact counts vary by tokenizer
- Dependencies: Steps 01-04 must have completed (or been skipped where appropriate)

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
| Managed section (all skills) | {n} | ~{t} | In {target-file}, all {count} skills |
| SKILL.md | {n} | ~{t} | Active skill (on-trigger) |
| metadata.json | {n} | ~{t} | Machine-readable |
| references/ | {n} | ~{t} | {count} files |
| **Package total** | **{n}** | **~{t}** | **All artifacts combined** |

**Context Budget Impact:**
- **Always-on cost:** ~{managed-section-tokens} tokens (managed section in {target-file})
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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All artifacts measured with consistent heuristic
- Clear table format with words and estimated tokens
- Context budget impact explained (always-on vs on-trigger vs full)
- Benchmark comparison for managed section target
- Passive context opt-out correctly handled (skip snippet/section measurements)
- Auto-proceed to step-06

### ❌ SYSTEM FAILURE:

- Not measuring all artifacts
- Inconsistent estimation method
- Not explaining context budget impact
- Modifying any files (read-only step)
- Not auto-proceeding after report

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
