---
nextStepFile: 'generate-briefs.md'
outputFile: '{forge_data_folder}/analyze-source-report-{project_name}.md'
schemaFile: 'assets/skill-brief-schema.md'
discoverFile: 'references/discover-additional-source.md'
advancedElicitationSkill: '/bmad-advanced-elicitation'
partyModeSkill: '/bmad-party-mode'
---

<!-- Config: communicate in {communication_language}. Artifact text in {document_output_language}. -->

# Step 5: Recommend

## STEP GOAL:

To present each qualifying unit as a recommendation with evidence-based rationale, allow the user to confirm, reject, or modify each recommendation, and build the confirmed units list that drives brief generation.

## Rules

- This is the primary user decision point: every unit gets a decision before the run moves on, which a headless run takes by the §7 GATE default
- Present evidence for each recommendation, invite questions and pushback

## MANDATORY SEQUENCE

Every HARD HALT in this step names its exit code, `halt_reason` and phase. When `{headless_mode}` is true it first prints its envelope on stderr through the shared emitter (`{emitEnvelopeHelper}` and `{run_dir}` come from SKILL.md On Activation): stage `{run_dir}/halt.json` as `{"phase": "<phase>", "reason": "<the halt message>", "halt_reason": "<halt_reason>", "mode": "interactive", "report_path": "{outputFile as an absolute path}"}`, plus `"path"` when the halt names one, then run

```bash
uv run {emitEnvelopeHelper} emit-halt --workflow skf-analyze-source --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

and display the line it prints verbatim. Write the payload as valid JSON: in the halt message and `path`, replace each backslash with / and each double quote with a backtick. If the emitter exits non-zero or prints no line, display the halt message alone. An interactive HALT displays its message and emits nothing.

### 1. Load Context

Read {outputFile} completely to obtain:
- Qualifying units from Identified Units, each with its project path (the deferred ones are listed in the summary, not given a card)
- Export map data per unit
- Integration points and coupling analysis
- Stack skill candidates from frontmatter
- Existing skills from frontmatter
- `intent_hint` from frontmatter (the goal the user stated at init; empty when none)
- `refs` from frontmatter: a unit's ref is its project path's entry there (none without one)

Load {schemaFile} for reference on what skill-brief.yaml requires (so recommendations are actionable).

**Apply `intent_hint` when ranking units.** If `intent_hint` is non-empty, use it to bias the order in which recommendation cards are presented and to soften the rationale for units that fall outside the stated intent (e.g., when `intent_hint` mentions "authentication and authorization", rank auth-related units first and flag unrelated units with a one-line rationale acknowledging the mismatch). If `intent_hint` is empty, present in the deterministic order from the export map.

### 2. Build Recommendation Cards

For each qualifying unit, prepare a recommendation card:

```
**Unit: {name}**
- Source: {its project path}{, at {its ref} when it has one}
- Path: {path}
- Language: {language}
- Boundary: {type} | Scope: {scope_type}
- Exports: {count} ({pattern})
- API Surface: {size}
- Integrations: imports from {list}, imported by {list}
- Coupling: {tight/loose/indirect}
- Confidence: {high/medium/low}
- Stack Skill: {yes — grouped with {units} / no}
- Status: {new / briefed: a brief from an earlier analysis at {its path}, rewritten if you confirm the unit / already-skilled → recommend update-skill}

**Rationale:** {2-3 sentences explaining WHY this should be a skill, citing specific detection signals and file paths}

**Proposed Brief Fields:**
- name: {the unit's name, as identify-units or map-and-detect derived it}
- scope.type: {full-library / specific-modules / public-api / component-library / reference-app / docs-only}
- scope.include: {suggested glob patterns}
- description: {suggested 1-3 sentence description, containing a literal `Use when` clause}
```

### 3. Present Recommendations

**Headless** (`{headless_mode}` true): no one answers the questions below. Take the §7 GATE default now (confirm every card as proposed and flag every stack skill candidate for create-stack-skill), record it as that GATE says, then continue at §6. No question of §3 to §5 is asked.

"**Recommendations for {project_name}**

I've analyzed {count} qualifying units. Here are my recommendations for skill creation:

---"

Present each recommendation card, then after ALL cards:

"---

**Summary:**
- **Recommended for new skills:** {count}
- **Already-skilled (recommend update-skill):** {count}
- **Stack skill candidates:** {count}
- **Deferred (outside the stated goal, not analyzed):** {count, with their names}

**For each unit above, please indicate:**
- **Y**: Confirm: generate skill-brief.yaml
- **N**: Reject: skip this unit
- **M**: Modify: adjust name, scope, or description before confirming

**Bulk shortcuts:**
- `all-Y`: confirm every recommendation as-is
- `all-N`: skip every recommendation
- Individual response list (e.g., `1:Y, 2:N, 3:M, ...`): explicit per-unit decisions (use this when you want to mix Y/N/M or modify any unit)

**Questions?** Ask 'why?' about any recommendation and I'll explain my reasoning with specific evidence."

### 4. Process User Decisions

Record a decision for every unit before moving on: Y adds it to `confirmed_units` with its proposed brief fields; N records the user's reason; M asks what to change (name, scope type, include patterns, description), applies it and confirms the result.

### 5. Confirm Stack Skill Candidates

If stack skill candidates were flagged, list them (units, detection signal, evidence): their units show strong co-integration patterns and may benefit from a consolidated stack skill via create-stack-skill. Ask "Flag these for create-stack-skill? (Y/N per candidate)" and record each decision.

### 6. Append to Report

Replace `[Appended by recommend]` in {outputFile} with:
- All recommendation cards (including rationale)
- User decisions per unit (confirmed/rejected/modified)
- Stack skill candidate decisions

Update {outputFile} frontmatter:
```yaml
confirmed_units: [{list of confirmed unit names}]
stack_skill_candidates: [{updated list with user decisions}]
```

A later pass through this section (after [A], [P] or [D], or in a session that resumed this step) replaces what the earlier one wrote. The step is marked complete only when [C] leaves it, so a run cancelled at the §7 menu resumes at these recommendations.

### 7. Present MENU OPTIONS

Lead with the decisions, so the menu is chosen against the final list:

"**Confirmed for brief generation:** {count}: {each confirmed unit with its final name, scope type and description}
**Rejected:** {count}: {each with its reason}
**Flagged for create-stack-skill:** {count}: {each grouping}"

Display: "**Select an Option:** [A] Advanced Elicitation [P] Party Mode [D] Discover Additional Source [C] Continue to Brief Generation [X] Cancel and exit"

#### Menu Handling Logic:

- IF A: Invoke {advancedElicitationSkill}. For each unit what it surfaced changes, take the decision again as §4 says, redo §6, then redisplay this menu
- IF P: Invoke {partyModeSkill}, then handle what it surfaced as [A] does
- IF D: load, read the entire file, then execute {discoverFile} with the project path the user gives. It returns the new path's units with their export records and composite proposals. Present each proposal (accepted unless the user rejects it; an accepted one replaces its constituents as one unit and joins `confirmed_composites` in the frontmatter), build the cards of the new units (§2), take their decisions (§3 to §5), redo §6, then redisplay this menu
- IF C: update {outputFile} frontmatter (`stepsCompleted`: append `recommend`; `lastStep: 'recommend'`), then load, read the entire file, then execute {nextStepFile}
- IF X: HARD HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `recommend:7`, with `unit_counts` reflecting the decisions made so far in its payload): "Cancelled at the recommendations."
- IF Any other comments or queries: help user respond then [Redisplay Menu Options](#7-present-menu-options)

**GATE [default: C]**: present the menu and wait for the user's choice. The default also answers every question of §3 to §5: confirm every card as proposed and flag every stack skill candidate. If `{headless_mode}`, §3 takes that default before any question and records it the moment it does: stage `{run_dir}/decision.json` as `{"gate": "recommend.recommendations", "default_action": "C", "taken_action": "C", "reason": "headless: auto-accept all recommendations and flag every stack skill candidate", "evidence": {"confirmed": [<each confirmed unit name>], "stack_skill_candidates": <the flagged candidate count>}}`, then run

```bash
uv run {emitEnvelopeHelper} record --workflow skf-analyze-source --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"
```

If the command fails, go on: only that entry is lost. At this menu a headless run continues with [C].
