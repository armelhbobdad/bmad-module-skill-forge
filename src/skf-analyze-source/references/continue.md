---
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
nextStepOptions:
  step 1a: 'step-auto-scope.md'
  step 2: 'scan-project.md'
  step 3: 'identify-units.md'
  step 4: 'map-and-detect.md'
  step 5: 'recommend.md'
  step 6: 'generate-briefs.md'
  step 7: 'health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1b: Continue Analysis

## STEP GOAL:

To resume the analyze-source workflow from where it was left off in a previous session by reading the analysis report's progress state and routing to the correct next step.

## Rules

- Focus only on reading state and routing — do not perform any analysis
- Do not re-run completed steps
- Present progress summary to user before resuming

## MANDATORY SEQUENCE

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
- `mode` — `'auto'` when the report was produced by the auto-scope path; absent or any other value means interactive

### 3. Present Progress Summary

"**Analysis Progress for {project_name}:**

**Project:** {project_paths}
**Forge Tier:** {forge_tier}
**Steps Completed:** {list stepsCompleted}
**Last Step:** {last entry in stepsCompleted}

**Progress:**
{For each completed step, summarize what was accomplished — read the relevant sections from the report}"

### 4. Determine Next Step

**IF the report's `mode` is `'auto'`** (produced by the auto-scope path; reached here because the resume invocation did not carry `[auto]`): an auto analysis is a single idempotent pass, not a resumable interactive chain. Do not use the interactive table below.
- If `auto-scope` is in `stepsCompleted`, the auto analysis already completed — announce "**This auto analysis is already complete.** Would you like to start a new analysis?" and stop.
- Otherwise (an auto run interrupted before auto-scope finished), re-enter the auto path: load, read fully, then execute `step-auto-scope.md` (it reads the existing report frontmatter and re-runs cleanly). **STOP HERE.**

For interactive reports, map the last completed step to the next step file:

| Last Completed | Next Step |
|----------------|-----------|
| init | scan-project |
| scan-project | identify-units |
| identify-units | map-and-detect |
| map-and-detect | recommend |
| recommend | generate-briefs |
| generate-briefs | health-check |

**IF `health-check` is in `stepsCompleted`:**
"**This analysis appears to be complete.** All steps have been finished. Would you like to start a new analysis?"

### 5. Update and Route

Update {outputFile} frontmatter:
```yaml
lastContinued: '{current_date}'
```

"**Resuming from {next_step_name}...**"

Auto-proceed: immediately load, read the entire file, then execute the next incomplete step from {nextStepOptions}.

