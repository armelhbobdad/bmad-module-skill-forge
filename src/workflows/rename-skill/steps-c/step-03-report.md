---
name: 'step-03-report'
description: 'Report rename operation results'
---

# Step 3: Report Rename Results

## STEP GOAL:

Present a clear, final summary of what the rename workflow changed — old and new names, versions renamed, file-level update counts, manifest re-key, platform context rebuild, and any residual warnings or deletion errors — so the user can verify the outcome and know whether any manual follow-up is required.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER modify any files in this step — report only
- 📖 CRITICAL: Read the complete step file before taking any action
- 📋 YOU ARE A FACILITATOR, summarizing what step-02 already executed
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are Ferris in Management mode — summarizing a transactional rename with precision
- ✅ Be explicit about what changed and what did not — no glossing over partial failures
- ✅ Surface every warning and deletion error so the user knows exactly where manual cleanup is required

### Step-Specific Rules:

- 🎯 Focus only on reporting the results stored in context by step-02
- 🚫 FORBIDDEN to re-execute any part of the rename
- 🚫 FORBIDDEN to hide verification warnings, platform rebuild failures, or deletion errors
- 💬 Present the "next steps" guidance so the user knows which downstream workflows to run

## EXECUTION PROTOCOLS:

- 🎯 Render the report using the context values set in step-02 (`old_name`, `new_name`, `affected_versions`, `affected_versions_count`, `files_updated_per_version`, `manifest_rekeyed`, `platform_files_updated`, `platform_files_failed`, `section2_warnings`, `section3_warnings`, `verification_warnings`, `deletion_errors`)
- 💬 Include the "next steps" block unconditionally — it captures the common follow-ups for any rename

## CONTEXT BOUNDARIES:

- Available: All decision and result values stored in context by step-01 and step-02
- Focus: Rendering the final report
- Limits: No file writes, no deletions, no further execution
- Dependencies: Step-02 must have completed (or attempted all sections through section 8) and stored its results

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly.

### 1. Render the Report

Display the following block, filling in values from context:

```
**Rename complete.**

From: {old_name}
To:   {new_name}

Versions renamed: {affected_versions_count} ({comma-separated affected_versions})

References updated:
  - SKILL.md frontmatter       (×{affected_versions_count})
  - metadata.json              (×{affected_versions_count})
  - context-snippet.md         (×{affected_versions_count})
  - provenance-map.json        (×{affected_versions_count})

Manifest updated: {if manifest_rekeyed: "exports.{new_name} (re-keyed from exports.{old_name})" else: "(no manifest entry existed for {old_name})"}
Platform files rebuilt: {list from platform_files_updated, or "(none)"}
{if platform_files_failed is non-empty:}
Platform files FAILED: {list from platform_files_failed}
  → Re-run `[EX] Export Skill` to retry the managed section rebuild for these files.

{if section2_warnings is non-empty:}
Warnings (inner directory rename):
  {list each warning from section2_warnings}

{if section3_warnings is non-empty:}
Warnings (missing files during content update):
  {list each warning from section3_warnings}

{if verification_warnings is non-empty:}
Informational: the old name still appears in SKILL.md body text (prose only, non-structural) in:
  {list each path from verification_warnings}
  → These are typically historical notes or changelog entries. Review and edit manually if you want them updated.

{if deletion_errors is non-empty:}
**Post-commit deletion errors:**
  {list each error}
  → The new name is fully committed. Remove the remnants manually with `rm -rf {path}`.

---

**Next steps:**
  - Run `@Ferris EX` if you want to re-verify the managed sections in platform context files
  - If you had QMD collections or external tooling registered under `{old_name}`, re-run `@Ferris SF` (or your registration command) to re-index under `{new_name}`
  - If this skill was published to agentskills.io under `{old_name}`, the registry version is unchanged — this rename is a LOCAL operation only
```

### 2. Close the Workflow

After rendering the report, the workflow is complete. Do not load any further step file — there is no `nextStepFile`.

## CRITICAL STEP COMPLETION NOTE

This is the final step. Once the report has been rendered, the rename-skill workflow is finished. Do not re-run any earlier step automatically — if the user wants another rename, they should re-invoke the workflow from the top.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Report rendered with old name, new name, and affected version list
- Per-file update counts stated explicitly (SKILL.md, metadata.json, context-snippet.md, provenance-map.json)
- Manifest re-key outcome clearly stated
- Platform files rebuilt listed (and failures surfaced when present)
- All warning categories surfaced (inner rename, missing files, informational body-text mentions)
- Post-commit deletion errors surfaced with manual cleanup guidance
- Next-steps block included unconditionally
- No further file writes or executions performed

### ❌ SYSTEM FAILURE:

- Hiding failed platform rebuilds, verification warnings, or deletion errors
- Reporting "complete" when step-02 partially failed without flagging it
- Re-executing any part of the rename workflow
- Omitting the next-steps guidance
- Reading stale context values instead of the post-rename state stored by step-02

**Master Rule:** The report must be an honest, complete summary of what step-02 actually did. Every partial failure must be visible so the user knows exactly what manual follow-up, if any, is required.
