---
nextStepFile: '../../shared/health-check.md'
---

# Step 3: Report Drop Results

## STEP GOAL:

Present a clear, final summary of what the drop workflow changed — manifest state, platform context files, deleted directories, disk freed, and remaining versions — so the user can verify the outcome and know whether any manual follow-up is required.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER modify any files in this step — report only
- 📖 CRITICAL: Read the complete step file before taking any action
- 📋 YOU ARE A FACILITATOR, summarizing what step-02 already executed
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are Ferris in Management mode — summarizing a destructive operation with precision
- ✅ Be explicit about what changed and what did not — no glossing over partial failures
- ✅ Surface recovery guidance when any stage in step-02 reported an error

### Step-Specific Rules:

- 🎯 Focus only on reporting the results stored in context by step-02
- 🚫 FORBIDDEN to re-execute any part of the drop
- 🚫 FORBIDDEN to hide verification errors or failed platform rebuilds
- 💬 Present the final state clearly, including remaining versions for the affected skill

## EXECUTION PROTOCOLS:

- 🎯 Render the report using the context values set in step-02 (`target_skill`, `target_versions`, `drop_mode`, `is_skill_level`, `files_deleted`, `disk_freed`, `manifest_updated`, `platform_files_updated`, `platform_files_failed`, `verification_errors`)
- 📖 For the "remaining versions" section, re-read `{skills_output_folder}/.export-manifest.json` (already updated by step-02) to show the current state
- 💬 Include the reversibility note only when `drop_mode == "deprecate"`

## CONTEXT BOUNDARIES:

- Available: All decision and result values stored in context by step-01 and step-02, plus the updated export manifest on disk
- Focus: Rendering the final report
- Limits: No file writes, no deletions, no further execution
- Dependencies: Step-02 must have completed (or attempted all stages) and stored its results

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly.

### 1. Determine Remaining Versions

**If `is_skill_level == true`:**

Set `remaining_versions_display = "(skill fully removed)"`.

**If `is_skill_level == false`:**

Read `{skills_output_folder}/.export-manifest.json` and look up `exports.{target_skill}.versions`. Build a human-readable list of every remaining version with its status, with the active one marked:

```
  - 0.1.0 (deprecated)
  - 0.5.0 (archived)
  - 0.6.0 (active) *
```

### 2. Render the Report

Display the following block, filling in values from context:

```
**Drop operation complete.**

Operation:     {Deprecate | Purge}
Skill:         {target_skill}
Version(s):    {comma-separated target_versions or "ALL"}

Changes:
- Manifest updated:      {yes | no}
- Platform files rebuilt: {list from platform_files_updated, or "(none)"}
{if platform_files_failed is non-empty:}
- Platform files FAILED: {list from platform_files_failed}
{if drop_mode == "purge":}
- Files deleted:         {list from files_deleted, or "(none — nothing on disk)"}
- Disk space freed:      {disk_freed}

Remaining versions for {target_skill}:
{remaining_versions_display}

{if drop_mode == "deprecate":}
**Note:** Files remain on disk. This operation is reversible by manually editing
`{skills_output_folder}/.export-manifest.json` and changing the version's `status`
field back to `"active"` or `"archived"`, then re-running `[EX] Export Skill` to
restore the managed section entry.

{if verification_errors is non-empty:}
**Verification warnings:**
{list each verification error}
These require manual review — see the error-handling guidance in step-02.
```

### 3. Workflow Health Check

Load and execute `{nextStepFile}` for workflow self-improvement check.

## CRITICAL STEP COMPLETION NOTE

This step chains to the shared health check. After the health check completes, the drop-skill workflow is fully done. Do not re-run any earlier step automatically — if the user wants another drop, they should re-invoke the workflow from the top.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Report rendered with operation type, skill, version(s), and mode
- Manifest update outcome clearly stated (yes/no)
- Platform files rebuilt listed (and failures surfaced when present)
- Purge mode: files deleted and disk freed reported
- Soft drop: reversibility note included with concrete instructions
- Remaining versions for the affected skill accurately listed from the updated manifest (or "(skill fully removed)" for skill-level drops)
- Verification warnings surfaced, not hidden
- No further file writes or executions performed

### ❌ SYSTEM FAILURE:

- Hiding failed platform rebuilds or verification errors
- Reporting "complete" when step-02 partially failed without flagging it
- Reading stale manifest data instead of the post-drop state
- Re-executing any part of the drop workflow
- Omitting the reversibility note in soft drop mode
- Displaying remaining versions from memory rather than from the updated manifest

**Master Rule:** The report must be an honest, complete summary of what step-02 actually did. Every partial failure must be visible so the user knows exactly what manual follow-up, if any, is required.
