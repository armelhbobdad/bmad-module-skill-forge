---
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
nextStepOptions:
  step 2: 'scan-project.md'
  step 3: 'identify-units.md'
  step 4: 'map-and-detect.md'
  step 5: 'recommend.md'
  step 6: 'generate-briefs.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 1b: Continue Analysis

## STEP GOAL:

To resume an unfinished analyze-source run from where a previous session left off, by reading the analysis report's progress state and routing to the correct next step. Init section 1 sends only an unfinished report of the step-by-step analysis here: it archives a finished report and one whose `mode` is `'auto'` and starts a fresh analysis instead.

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
| init | scan-project |
| scan-project | identify-units |
| identify-units | map-and-detect |
| map-and-detect | recommend |
| recommend | generate-briefs |

### 5. Update and Route

Update {outputFile} frontmatter:
```yaml
lastContinued: '{current_date}'
```

"**Resuming from {next_step_name}...**"

Auto-proceed: immediately load, read the entire file, then execute the next incomplete step from {nextStepOptions}.

