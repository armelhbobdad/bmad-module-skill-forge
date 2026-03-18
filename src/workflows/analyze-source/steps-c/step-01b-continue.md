---
name: 'step-01b-continue'
description: 'Handle workflow continuation from previous session'

outputFile: '{output_folder}/analyze-source-report-{project_name}.md'
nextStepOptions:
  step-02: './step-02-scan-project.md'
  step-03: './step-03-identify-units.md'
  step-04: './step-04-map-and-detect.md'
  step-05: './step-05-recommend.md'
  step-06: './step-06-generate-briefs.md'
---

# Step 1b: Continue Analysis

## STEP GOAL:

To resume the analyze-source workflow from where it was left off in a previous session by reading the analysis report's progress state and routing to the correct next step.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a source code analyst and decomposition architect (Ferris Architect mode)
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Prescriptive precision — resume exactly where we left off

### Step-Specific Rules:

- 🎯 Focus only on reading state and routing — do NOT perform any analysis
- 🚫 FORBIDDEN to re-run completed steps
- 💬 Present progress summary to user before resuming

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Update lastContinued in output frontmatter
- 📖 Route to the correct next step based on stepsCompleted
- 🚫 FORBIDDEN to skip the progress summary

## CONTEXT BOUNDARIES:

- Available: Existing analysis report with stepsCompleted array
- Focus: State detection and routing only
- Limits: Do not modify any existing report content
- Dependencies: Output file must exist with valid stepsCompleted

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Welcome Back

"**Welcome back!** Let me check where we left off with the source analysis..."

### 2. Read Progress State

Load {outputFile} and read frontmatter:
- `stepsCompleted` array
- `project_paths`
- `project_name`
- `forge_tier`
- `existing_skills`
- `confirmed_units`

### 3. Present Progress Summary

"**Analysis Progress for {project_name}:**

**Project:** {project_paths}
**Forge Tier:** {forge_tier}
**Steps Completed:** {list stepsCompleted}
**Last Step:** {last entry in stepsCompleted}

**Progress:**
{For each completed step, summarize what was accomplished — read the relevant sections from the report}"

### 4. Determine Next Step

Map the last completed step to the next step file:

| Last Completed | Next Step |
|----------------|-----------|
| step-01-init | step-02-scan-project |
| step-02-scan-project | step-03-identify-units |
| step-03-identify-units | step-04-map-and-detect |
| step-04-map-and-detect | step-05-recommend |
| step-05-recommend | step-06-generate-briefs |

**IF all steps completed:**
"**This analysis appears to be complete.** All steps have been finished. Would you like to start a new analysis?"

### 5. Update and Route

Update {outputFile} frontmatter:
```yaml
lastContinued: '{current_date}'
```

"**Resuming from {next_step_name}...**"

#### Menu Handling Logic:

- After progress is confirmed, immediately load, read entire file, then execute the appropriate step from {nextStepOptions}

#### EXECUTION RULES:

- This is an auto-proceed continuation step
- Route directly to the next incomplete step

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the progress state has been read, summarized to the user, and lastContinued updated will you load the appropriate next step file to resume the workflow.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Analysis report loaded and progress state read
- Progress summary presented to user
- Correct next step identified from stepsCompleted
- lastContinued updated in frontmatter
- Routed to correct step file

### ❌ SYSTEM FAILURE:

- Not reading stepsCompleted from report
- Skipping progress summary
- Routing to wrong step
- Re-running already completed steps
- Not updating lastContinued

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
