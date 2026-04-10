---
tierRulesData: 'references/tier-rules.md'
nextStepFile: 'shared/health-check.md'
---

# Step 4: Forge Status Report

## STEP GOAL:

Display the forge status report with positive capability framing and report tier changes on re-run.

## Rules

- Focus only on displaying the status report
- Do not use negative framing ("missing", "lacking", "unavailable")
- Do not list tools that are not available
- Use tier capability descriptions from tier-rules.md
- Chains to shared health check via `{nextStepFile}` after completion

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
  {if hygiene_stale_cleaned > 0: {hygiene_stale_cleaned} stale QMD registry entry/entries cleaned}
  {end if}

  {if ccc_registry_stale_cleaned > 0:}
  CCC Registry: {ccc_registry_stale_cleaned} stale entry/entries cleaned
  {end if}

  {if hygiene_result is "completed" and hygiene_healthy is 0:}
  QMD Registry: empty — collections are created automatically when you run [CS] Create Skill.
  {end if}

  {if tools.ccc is true:}
  CCC Index:
  {if ccc_index_result is "fresh": up to date — semantic discovery ready}
  {if ccc_index_result is "created": indexed this run — semantic discovery ready}
  {if ccc_index_result is "failed": indexing failed — semantic discovery unavailable this session}
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

### 3. Workflow Health Check

Load and execute `{nextStepFile}` for workflow self-improvement check.

## CRITICAL STEP COMPLETION NOTE

This step chains to the shared health check. After the health check completes, the setup workflow is fully done.

