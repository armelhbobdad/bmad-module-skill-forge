---
name: 'step-04-update-context'
description: 'Update managed section in CLAUDE.md/AGENTS.md with four-case logic per ADR-J'

nextStepFile: './step-05-token-report.md'
managedSectionData: '../data/managed-section-format.md'
---

# Step 4: Update Context

## STEP GOAL:

To update the managed `<!-- SKF:BEGIN/END -->` section in the platform-appropriate context file (CLAUDE.md/AGENTS.md/.cursorrules) using the four-case logic defined by ADR-J (Create, Append, Regenerate, Malformed Markers halt), rebuilding the complete skill index from all exported skills.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER modify content outside `<!-- SKF:BEGIN/END -->` markers
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a delivery and packaging specialist in Ferris Delivery mode
- ✅ If you already have been given a name, communication_style and identity, continue to use those while playing this new role
- ✅ Surgical precision required — existing file content MUST be preserved
- ✅ User confirms changes before any writes to shared context files

### Step-Specific Rules:

- 🎯 Focus only on the managed section update in the target context file
- 🚫 FORBIDDEN to modify ANY content outside `<!-- SKF:BEGIN -->` and `<!-- SKF:END -->` markers
- 🚫 FORBIDDEN to write without user confirmation — this modifies shared project files
- 💬 Show a clear diff preview before writing
- 📋 If `passive_context: false` was detected in step-01, SKIP this step entirely and auto-proceed

## EXECUTION PROTOCOLS:

- 🎯 Follow the MANDATORY SEQUENCE exactly
- 💾 Load {managedSectionData} for format template and three-case logic
- 📖 Rebuild the COMPLETE skill index — not just the current skill
- 🚫 ZERO data loss — verify preserved content before and after write

## CONTEXT BOUNDARIES:

- Available: Skill metadata from step-01, context-snippet.md from step-03, platform flag
- Focus: Three-case detection and managed section update
- Limits: Only modify content between markers — preserve everything else
- Dependencies: Step-03 must have generated the snippet (or step skipped if passive_context off)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Check Passive Context Setting

**If `passive_context: false` was detected in step-01:**

"**Passive context disabled in preferences.yaml. Skipping context update.**"

Auto-proceed immediately to {nextStepFile}.

**If `passive_context: true` (default):** Continue to step 2.

### 2. Load Managed Section Format

Load {managedSectionData} and read the complete format template and three-case logic.

### 3. Determine Target File

Based on the `--platform` flag parsed in step-01:

| Platform | Target File |
|----------|-------------|
| `claude` (default) | CLAUDE.md |
| `cursor` | .cursorrules |
| `copilot` | AGENTS.md |

Resolve target file path at project root: `{project-root}/{target-file}`

### 4. Rebuild Complete Skill Index

#### 4a. Read Export Manifest

Read `{skills_output_folder}/.export-manifest.json`:

**If the file exists:** Parse JSON. The manifest tracks which skills have been explicitly exported:

```json
{
  "exports": {
    "skill-name": {
      "platforms": ["claude"],
      "last_exported": "YYYY-MM-DD"
    }
  }
}
```

**If the file does not exist** (first export or migration): Treat as empty — only the current export target will appear in the rebuilt index.

#### 4b. Build Exported Skill Set

Determine the set of skills to include in the rebuilt index:

1. Start with all skill names listed in the manifest's `exports` object (if manifest exists)
2. Add the current export target skill name (ensures it is always included even before manifest is written)
3. This is the **exported skill set**

#### 4c. Scan and Filter Snippets

Scan `{skills_output_folder}/*/context-snippet.md` to find snippet files on disk.

**For each found context-snippet.md:**
1. Extract the skill name from the directory path
2. **If the skill name is in the exported skill set:** Read snippet content, add to skill index
3. **If the skill name is NOT in the exported skill set:** Skip — this skill has not been through export-skill and must not appear in the managed section (ADR-K)

**If no snippets pass the filter:** Generate managed section with zero skills — header only, no skill entries.

**Sort skills alphabetically by name.**

Count totals:
- Total skills (single type)
- Total stack skills

### 5. Generate Managed Section

Assemble the complete managed section:

```markdown
<!-- SKF:BEGIN updated:{current-date} -->
[SKF Skills]|{n} skills|{m} stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|{skill-snippet-1}
|
|{skill-snippet-2}
|
|{skill-snippet-N}
<!-- SKF:END -->
```

### 6. Detect Case and Prepare Changes

**Check target file at `{project-root}/{target-file}`:**

**Case 1: Create (file does not exist)**
- Action: Create new file with managed section only
- Diff: Show entire managed section as new content

**Case 2: Append (file exists, no `<!-- SKF:BEGIN` marker found)**
- Action: Read existing content, append managed section at end
- Diff: Show managed section being appended after existing content
- Preserved: ALL existing content untouched

**Case 3: Regenerate (file contains `<!-- SKF:BEGIN` and `<!-- SKF:END -->`)**
- Action: Replace everything between markers (inclusive) with new managed section
- Diff: Show old managed section vs new managed section
- Preserved: ALL content before `<!-- SKF:BEGIN` and after `<!-- SKF:END -->`

**Case 4: Malformed markers (file contains `<!-- SKF:BEGIN` but no `<!-- SKF:END -->`)**
- Action: HALT with warning: "Malformed SKF markers detected in `{target-file}` — `<!-- SKF:BEGIN` found but `<!-- SKF:END -->` is missing. Please restore the end marker manually before running export."
- Do NOT attempt to write or append — the file is in an inconsistent state

### 7. Present Change Preview

"**Context update prepared.**

**Target:** `{project-root}/{target-file}`
**Case:** {1: Create / 2: Append / 3: Regenerate}
**Skills in index:** {n} skills, {m} stack

**Changes:**

{Show diff preview:}
- For Case 1: Show full file content to be created
- For Case 2: Show `...existing content preserved...\n\n{managed section}`
- For Case 3: Show old section vs new section with surrounding context preserved

**Content outside markers:** {preserved / n/a (new file)}

**Ready to write changes?**"

### 8. Present MENU OPTIONS

**If dry-run mode:**

"**[DRY RUN] No files will be written. Preview above shows what would change.**

**Proceeding to token report...**"

Auto-proceed to {nextStepFile}.

**If NOT dry-run:**

Display: "**Select:** [C] Continue — write changes to {target-file}"

#### Menu Handling Logic:

- IF C: Write the changes to target file, verify write succeeded, then load, read entire file, then execute {nextStepFile}
- IF Any other: help user respond, then [Redisplay Menu Options](#8-present-menu-options)

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to next step when user selects 'C'
- In dry-run mode, auto-proceed without writing

### 9. Write and Verify (Non-Dry-Run Only)

After user confirms with 'C':

1. Write the file using the appropriate case logic
2. Re-read the written file
3. Verify `<!-- SKF:BEGIN` and `<!-- SKF:END -->` markers are present
4. Verify content outside markers is unchanged (for Cases 2 and 3)
5. Report: "**{target-file} updated successfully.** Verified: markers present, external content preserved."

**If verification fails:**
"**WARNING: Write verification failed.** {describe issue}. File may need manual review."

### 9b. Update Export Manifest (Non-Dry-Run Only)

After successful write and verification in section 9:

1. Read `{skills_output_folder}/.export-manifest.json` (or start with `{"exports": {}}` if it does not exist)
2. Add or update the current skill's entry:
   ```json
   "{skill-name}": {
     "platforms": ["{platform}"],
     "last_exported": "{current-date}"
   }
   ```
   - If the skill already has a manifest entry, merge the platform into the existing `platforms` array (deduplicate) and update `last_exported`
3. Write the updated manifest to `{skills_output_folder}/.export-manifest.json`

**Dry-run mode:** Do NOT update the manifest. Display: "**[DRY RUN] Export manifest would be updated for {skill-name} on platform {platform}.**"

**Error handling:** If manifest write fails, warn but do not fail the workflow — the managed section was already written successfully.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user confirms changes by selecting 'C' (or auto-proceed in dry-run) and the write is verified will you load and read fully `{nextStepFile}` to execute the token report.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Managed section format loaded from {managedSectionData}
- Target file correctly determined from platform flag
- Complete skill index rebuilt from exported skills only (filtered via .export-manifest.json per ADR-K)
- Export manifest updated after successful write (non-dry-run only)
- Correct case detected (create/append/regenerate)
- Clear diff preview shown to user
- User confirmation received before writing
- Write verified — markers present, external content preserved
- Passive context opt-out correctly handled (skip when disabled)
- Dry-run correctly handled (preview only, no writes)

### ❌ SYSTEM FAILURE:

- Modifying content outside `<!-- SKF:BEGIN/END -->` markers
- Not rebuilding the COMPLETE skill index (only adding current skill)
- Including un-exported skills in managed section (bypasses ADR-K publishing gate)
- Updating export manifest during dry-run
- Writing without user confirmation
- Not verifying write after completion
- Not detecting the correct case (create/append/regenerate)
- Losing existing file content during write
- Not skipping when passive_context is disabled

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE. ZERO data loss in target files is NON-NEGOTIABLE.
