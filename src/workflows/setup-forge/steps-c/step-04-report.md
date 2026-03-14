---
name: 'step-04-report'
description: 'Display forge status report with positive capability framing'

tierRulesData: '../data/tier-rules.md'
---

# Step 4: Forge Status Report

## STEP GOAL:

Display the forge status report with positive capability framing, report tier changes on re-run, and optionally fetch the latest agentskills.io spec if flagged.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🎯 Execute all operations autonomously — display report and complete

### Role Reinforcement:

- ✅ You are Ferris reporting forge readiness
- ✅ Frame ALL capabilities positively — describe what the tier GIVES
- ✅ On re-run: explicitly report what changed (upgrade/downgrade/same)
- ✅ Brief forge metaphor appropriate here — this is the completion moment

### Step-Specific Rules:

- 🎯 Focus only on displaying the status report
- 🚫 FORBIDDEN to use negative framing ("missing", "lacking", "unavailable")
- 🚫 FORBIDDEN to list tools that are NOT available
- 💬 Use tier capability descriptions from tier-rules.md

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Load tier-rules.md for capability descriptions and re-run messages
- 📖 Use context from step-01 (detected_tools, calculated_tier, previous_tier)
- 🚫 This is the final step — no next step to load

## CONTEXT BOUNDARIES:

- Available: {detected_tools}, {calculated_tier}, {previous_tier}, {tier_override} from step-01
- Available: tool version strings from step-01
- Available: {hygiene_result}, {hygiene_healthy}, {hygiene_orphaned_removed}, {hygiene_orphaned_kept}, {hygiene_stale_cleaned} from step-03
- Focus: report display only — no file modifications
- Dependencies: steps 01-03 must have completed

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Capability Descriptions

Load and read {tierRulesData} for the tier capability descriptions and re-run messages.

### 2. Display Forge Status Report

**Format the report as follows:**

```
═══════════════════════════════════════
  FORGE STATUS
═══════════════════════════════════════

  Tier:  {calculated_tier}
  {tier capability description from tier-rules.md}

  Tools Detected:
  {for each tool that is available, show: tool name — version}

  {if hygiene_result is "completed":}
  QMD Registry:
  {hygiene_healthy} collection(s) healthy
  {if hygiene_orphaned_removed > 0: {hygiene_orphaned_removed} orphaned collection(s) removed}
  {if hygiene_orphaned_kept > 0: {hygiene_orphaned_kept} orphaned collection(s) kept}
  {if hygiene_stale_cleaned > 0: {hygiene_stale_cleaned} stale registry entry/entries cleaned}
  {end if}

  {if hygiene_result is "completed" and hygiene_healthy is 0:}
  QMD Registry: empty — collections are created automatically when you run [CS] Create Skill.
  {end if}

{if tier_override is active:}
  Note: Tier override active (set in preferences.yaml)

{if re-run with tier change:}
  {appropriate upgrade/downgrade message from tier-rules.md}

{if re-run with same tier:}
  {same-tier message from tier-rules.md}

═══════════════════════════════════════
  Forge ready. {calculated_tier} tier active.
═══════════════════════════════════════
```

**Tool display rules:**
- Only show tools that ARE available with their version strings
- Do NOT list unavailable tools
- Do NOT show a "missing" column or section

### 3. Handle --update-spec Flag (Optional)

**If `--update-spec` was passed:**
- Attempt to fetch the latest agentskills.io specification schema
- Use `gh` or `curl` to retrieve the spec
- Store in `{project-root}/forge-data/agentskills-spec.json` (or appropriate format)
- If fetch succeeds: display "agentskills.io spec updated."
- If fetch fails: display "Could not fetch agentskills.io spec. Existing spec (if any) unchanged."
- Do NOT fail the workflow over this — it is purely optional

**If `--update-spec` was NOT passed:**
- Skip silently

### 4. Workflow Complete

This is the final step. The setup-forge workflow is now complete.

No next step to load. The workflow ends here.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Forge status report displayed with positive capability framing
- Only available tools shown (no "missing" lists)
- Tier capability description matches calculated tier
- Re-run: tier change correctly reported (or same-tier confirmed)
- --update-spec handled if flagged (success or graceful failure)
- Workflow completes cleanly

### ❌ SYSTEM FAILURE:

- Negative framing in report ("missing", "unavailable", "lacking")
- Listing tools that are NOT available
- Not using tier capability descriptions from tier-rules.md
- Not reporting tier change on re-run
- Attempting to load a next step (this is the final step)

**Master Rule:** The report must leave users feeling confident about their forge capabilities, not anxious about what they're missing. Positive framing only.
