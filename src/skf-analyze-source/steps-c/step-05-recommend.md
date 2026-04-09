---
nextStepFile: './step-06-generate-briefs.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
schemaFile: 'assets/skill-brief-schema.md'
advancedElicitationSkill: '/bmad-advanced-elicitation'
partyModeSkill: '/bmad-party-mode'
---

# Step 5: Recommend

## STEP GOAL:

To present each qualifying unit as a recommendation with evidence-based rationale, allow the user to confirm, reject, or modify each recommendation, and build the confirmed units list that drives brief generation.

## Rules

- This is the primary user decision point — do not rush through it
- Do not proceed without explicit confirmation for each unit
- Present evidence for each recommendation, invite questions and pushback

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Context

Read {outputFile} completely to obtain:
- Qualifying units from Identified Units
- Export map data per unit
- Integration points and coupling analysis
- Stack skill candidates from frontmatter
- Existing skills from frontmatter

Load {schemaFile} for reference on what skill-brief.yaml requires (so recommendations are actionable).

### 2. Build Recommendation Cards

For EACH qualifying unit, prepare a recommendation card:

```
**Unit: {name}**
- Path: {path}
- Language: {language}
- Boundary: {type} | Scope: {scope_type}
- Exports: {count} ({pattern})
- API Surface: {size}
- Integrations: imports from {list}, imported by {list}
- Coupling: {tight/loose/indirect}
- Confidence: {high/medium/low}
- Stack Skill: {yes — grouped with {units} / no}
- Status: {new / already-skilled → recommend update-skill}

**Rationale:** {2-3 sentences explaining WHY this should be a skill, citing specific detection signals and file paths}

**Proposed Brief Fields:**
- name: {suggested kebab-case name}
- scope.type: {full-library / specific-modules / public-api / component-library}
- scope.include: {suggested glob patterns}
- description: {suggested 1-3 sentence description}
```

### 3. Present Recommendations

"**Recommendations for {project_name}**

I've analyzed {count} qualifying units. Here are my recommendations for skill creation:

---"

Present each recommendation card, then after ALL cards:

"---

**Summary:**
- **Recommended for new skills:** {count}
- **Already-skilled (recommend update-skill):** {count}
- **Stack skill candidates:** {count}

**For each unit above, please indicate:**
- **Y** — Confirm: generate skill-brief.yaml
- **N** — Reject: skip this unit
- **M** — Modify: adjust name, scope, or description before confirming

You can respond with a list (e.g., '1:Y, 2:Y, 3:N, 4:M') or address each individually.

**Questions?** Ask 'why?' about any recommendation and I'll explain my reasoning with specific evidence."

### 4. Process User Decisions

For each unit:

**IF Y (Confirm):**
- Add to confirmed_units list with proposed brief fields

**IF N (Reject):**
- Document rejection with user's reason (if provided)
- Remove from confirmed list

**IF M (Modify):**
- Ask what to modify (name, scope, description, scope.include patterns)
- Update the recommendation with user changes
- Confirm the modified version

**Continue until ALL units have a decision (Y/N/M).**

### 5. Confirm Stack Skill Candidates

If stack skill candidates were flagged:

"**Stack Skill Candidates:**

The following unit groupings show strong co-integration patterns and may benefit from a consolidated stack skill via create-stack-skill:

{For each candidate: list units, detection signal, evidence}

Would you like to flag these for create-stack-skill? (Y/N per candidate)"

Document decisions.

### 6. Present Final Confirmation

"**Confirmed Units for Brief Generation:** {count}

{List each confirmed unit with final name, scope type, and description}

**Rejected Units:** {count}
{List with reasons}

**Stack Skill Flags:** {count}
{List groupings flagged for create-stack-skill}

**This is your final confirmation before I generate skill-brief.yaml files.** All confirmed?"

Wait for explicit final confirmation.

### 7. Append to Report

Append the complete "## Recommendations" section to {outputFile}:

Replace `[Appended by step-05-recommend]` with:
- All recommendation cards (including rationale)
- User decisions per unit (confirmed/rejected/modified)
- Stack skill candidate decisions
- Final confirmation status

Update {outputFile} frontmatter:
```yaml
stepsCompleted: [append 'step-05-recommend' to existing array]
lastStep: 'step-05-recommend'
confirmed_units: [{list of confirmed unit names}]
stack_skill_candidates: [{updated list with user decisions}]
```

### 8. Present MENU OPTIONS

Display: "**Select an Option:** [A] Advanced Elicitation [P] Party Mode [D] Discover Additional Source [C] Continue to Brief Generation"

#### Menu Handling Logic:

- IF A: Invoke {advancedElicitationSkill}, and when finished redisplay the menu
- IF P: Invoke {partyModeSkill}, and when finished redisplay the menu
- IF D: Accept a new repo path/URL from the user. Run a lightweight scan + classify (subset of steps 02-03) for the new source only. Merge new units into the existing report and update `project_paths[]` in frontmatter. Run export mapping for the new units (same logic as step 04 section 2). Generate recommendation cards for the new units and present them for confirmation. Then redisplay this menu.
- IF C: Save recommendations to {outputFile}, update frontmatter, then load, read entire file, then execute {nextStepFile}
- IF Any other comments or queries: help user respond then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- **GATE [default: C]** — If `{headless_mode}`: accept all recommendations and auto-proceed, log: "headless: auto-accept all recommendations"
- ONLY proceed to next step when user selects 'C'
- After other menu items execution, return to this menu
- User can chat or ask questions — always respond and then redisplay menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all units have explicit user decisions (Y/N/M), the confirmed_units list is finalized in frontmatter, and the user has given final confirmation, will you load and read fully {nextStepFile} to begin brief generation.

