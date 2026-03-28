---
name: 'step-04-confirm-brief'
description: 'Present complete skill brief for user review and confirmation before writing'

nextStepFile: './step-05-write-brief.md'
reviseStepFile: './step-03-scope-definition.md'
briefSchemaFile: '../data/skill-brief-schema.md'
advancedElicitationSkill: '/bmad-advanced-elicitation'
partyModeSkill: '/bmad-party-mode'
---

# Step 4: Confirm Brief

## STEP GOAL:

To present the complete skill brief in human-readable format, highlighting all fields that will be written to skill-brief.yaml, and obtain explicit user approval before writing.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE A FACILITATOR, not a content generator
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

### Role Reinforcement:

- ✅ You are a quality reviewer in Ferris Architect mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Present information precisely and clearly — this is a confirmation gate
- ✅ Highlight anything with low confidence or defaults that the user should verify

### Step-Specific Rules:

- 🎯 Focus only on presenting and confirming — do not write files yet (that's step 05)
- 🚫 FORBIDDEN to proceed without explicit user approval
- 💬 Approach: Prescriptive — exact presentation format showing all YAML fields
- 📋 This is a P2 confirmation gate — the user MUST approve before continuing

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Load the schema to ensure all required fields are presented
- 📖 This is a mandatory checkpoint — no auto-proceed
- 🚫 FORBIDDEN to write skill-brief.yaml in this step

## CONTEXT BOUNDARIES:

- Available context: All gathered data from steps 01-03 (target, intent, name, tier, language, scope)
- Focus: Presenting the complete brief for final review
- Limits: Do not write files — only present for approval
- Dependencies: Confirmed scope boundaries from step 03

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Schema

Load `{briefSchemaFile}` to reference required fields and the human-readable presentation format.

### 2. Assemble Complete Brief

Compile all gathered data from steps 01-03 into the complete brief:

- **name:** {skill name from step 01}
- **version:** {auto-detected from source, or "1.0.0" if not found — see schema for detection rules}
- **source_repo:** {target repo from step 01}
- **language:** {detected/confirmed language from steps 02-03}
- **description:** {derived from user intent in step 01}
- **forge_tier:** {tier from step 01}
- **created:** {current date}
- **created_by:** {user_name from config}
- **scope.type:** {scope type from step 03}
- **scope.include:** {include patterns from step 03}
- **scope.exclude:** {exclude patterns from step 03}
- **scope.notes:** {any scope notes from step 03}
- **source_type:** {source or docs-only, from step 01}
- **doc_urls:** {collected documentation URLs with labels, from steps 01/03 — include if source_type is "docs-only" or supplemental URLs were collected}
- **scripts_intent:** {detect/none/description from step 03, or "detect" if not explicitly set}
- **assets_intent:** {detect/none/description from step 03, or "detect" if not explicitly set}
- **source_authority:** {official/community/internal from step 01 — default "community"}

### 3. Present Brief for Review

Using the presentation format from the schema:

"**Please review the complete skill brief before I write it.**

---

```
Skill Brief: {name}
====================

Target:      {source_repo}
Language:    {language}
Forge Tier:  {forge_tier}
Description: {description}

Scope: {scope.type}
  Include: {scope.include patterns, one per line}
  Exclude: {scope.exclude patterns, one per line}
  Notes:   {scope.notes}

{If source_type is "docs-only":}
Source Type: docs-only
Doc URLs:
  {doc_urls, one per line with labels}

{If source_type is "source" AND supplemental doc_urls collected:}
Supplemental Docs:
  {doc_urls, one per line with labels}

{If scripts_intent or assets_intent was explicitly set (not default "detect"):}
Scripts:    {scripts_intent}
Assets:     {assets_intent}

Source Authority: {source_authority}

Version:    {version}
Created:    {created}
Created by: {created_by}
```

---"

### 4. Highlight Items Needing Attention

Flag any fields that may need review:

{If language was overridden or low confidence:}
"**Note:** Language was {auto-detected / manually overridden}."

{If description was derived (not stated by user):}
"**Note:** Description was derived from your stated intent. Adjust if needed."

{If forge tier was defaulted:}
"**Note:** Forge tier defaulted to Quick (no forge-tier.yaml found)."

{If any scope patterns seem broad or narrow:}
"**Note:** {specific observation about scope breadth}."

"**This is your last chance to make changes before writing the file.**

You can:
- Adjust any field by telling me what to change
- Revise scope boundaries by selecting [R]
- Proceed to write by selecting [C]"

### 5. Handle Inline Adjustments

If the user requests changes to specific fields (name, description, version, etc.):
- Make the adjustment
- Re-present the updated brief
- Return to the menu

### 6. Present MENU OPTIONS

Display: **Select an Option:** [R] Revise Scope [A] Advanced Elicitation [P] Party Mode [C] Approve and Write

#### Menu Handling Logic:

- IF R: Load, read entire file, then execute {reviseStepFile} to re-enter scope definition
- IF A: Invoke {advancedElicitationSkill}, and when finished redisplay the menu
- IF P: Invoke {partyModeSkill}, and when finished redisplay the menu
- IF C: Load, read entire file, then execute {nextStepFile}
- IF Any other comments or queries: help user respond, apply any field adjustments, re-present brief if changed, then [Redisplay Menu Options](#6-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to write step when user selects 'C'
- After other menu items execution, return to this menu
- User can chat, request field changes, or ask questions — always respond and then redisplay menu

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN C is selected and the user has explicitly approved the brief will you load and read fully `./step-05-write-brief.md` to write the skill-brief.yaml file.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Schema loaded for field reference
- Complete brief assembled from all gathered data
- Brief presented in human-readable format
- Low-confidence or defaulted fields highlighted
- User explicitly approved the brief
- Menu presented with revise option

### ❌ SYSTEM FAILURE:

- Writing skill-brief.yaml in this step (too early)
- Proceeding without explicit user approval
- Not presenting all required fields
- Not highlighting defaulted or low-confidence values
- Not offering the [R] Revise option

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
