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

### 3. Determine Target File(s)

Using the `target_platforms` list resolved in step-01, determine all target files:

| Platform | Target File |
|----------|-------------|
| `claude` | CLAUDE.md |
| `cursor` | .cursorrules |
| `copilot` | AGENTS.md |

For each platform in `target_platforms`, resolve target file path: `{project-root}/{target-file}`

**If multiple platforms:** Sections 4-9a execute as a loop — one full pass per target platform. Each iteration uses the same skill index but rewrites root paths per platform (section 4d) and writes to the platform-specific target file. Section 9b executes once after all iterations complete.

**Processing order:** Process platforms in the order listed in `target_platforms`.

### 4. Rebuild Complete Skill Index

#### 4a. Read Export Manifest (v2 — version-aware)

Read `{skills_output_folder}/.export-manifest.json` — see [knowledge/version-paths.md](../../../knowledge/version-paths.md) for the full v2 schema:

**If the file exists:** Parse JSON. Check for `schema_version` field:

**v2 manifest** (`schema_version: "2"`):
```json
{
  "schema_version": "2",
  "exports": {
    "skill-name": {
      "active_version": "0.6.0",
      "versions": {
        "0.5.0": {
          "platforms": ["claude"],
          "last_exported": "2026-03-15",
          "status": "archived"
        },
        "0.6.0": {
          "platforms": ["claude", "copilot"],
          "last_exported": "2026-04-04",
          "status": "active"
        }
      }
    }
  }
}
```

**v1 manifest** (no `schema_version` field — migrate in-place to v2):
1. For each entry in `exports`, read its `platforms` and `last_exported`
2. Resolve the skill's current version from `{resolved_skill_package}/metadata.json`
3. Wrap in v2 structure: set `active_version` to the resolved version, create a single entry in `versions` with `status: "active"`, the original `platforms`, and `last_exported`
4. Set `schema_version: "2"` at root
5. Hold the migrated structure in context (it will be written in section 9b)

**If the file does not exist** (first export or migration): Treat as empty — only the current export target will appear in the rebuilt index.

#### 4b. Build Exported Skill Set (version-aware)

Determine the set of skills to include in the rebuilt index:

1. Start with all skill names listed in the manifest's `exports` object (if manifest exists)
2. For each skill, record its `active_version` from the manifest (v2 schema)
3. Add the current export target skill name (ensures it is always included even before manifest is written) — use the version from `{resolved_skill_package}/metadata.json` as its `active_version`
4. This is the **exported skill set** — each entry has a skill name and its resolved `active_version`

#### 4c. Resolve and Filter Snippets (manifest-driven — replaces glob scan)

Instead of globbing `{skills_output_folder}/*/context-snippet.md`, resolve snippets from the exported skill set built in 4b:

**For each skill in the exported skill set:**
1. Resolve `{skill_package}` using the skill's `active_version`: `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/`
2. Read `{skill_package}/context-snippet.md`
3. **If snippet exists:** Add to skill index
4. **If snippet does not exist at the versioned path:** Check for `active` symlink at `{skills_output_folder}/{skill-name}/active/{skill-name}/context-snippet.md`. If still not found, skip with warning: "Snippet missing for {skill-name} v{active_version} — skipping from managed section"

**Skills NOT in the exported skill set are never scanned** — they have not been through export-skill and must not appear in the managed section (ADR-K).

**If no snippets pass the filter:** Generate managed section with zero skills — header only, no skill entries.

#### 4d. Rewrite Root Paths for Target Platform

The context-snippet.md files on disk contain root paths for the platform they were originally exported to. When assembling the managed section for the current target platform, rewrite root paths if they differ:

**Platform root path mapping:**

| Platform | Root Path Prefix |
|----------|-----------------|
| `claude` | `.claude/skills/` |
| `cursor` | `.cursor/skills/` |
| `copilot` | `.agents/skills/` |
| _(legacy)_ | `skills/` |

The legacy `skills/` prefix may appear in snippets exported before platform-aware root paths were introduced, or in draft snippets generated by create-skill/quick-skill.

For each snippet being included in the managed section:

1. Read the `root:` value from the snippet's first line
2. Detect the current root prefix by matching against the known prefixes above (check platform-specific prefixes first, then fall back to legacy `skills/`)
3. If the detected prefix does not match the current target platform's prefix, rewrite it
4. Example: if snippet has `root: .claude/skills/my-lib/` but target is `cursor`, rewrite to `root: .cursor/skills/my-lib/`
5. Example: if snippet has legacy `root: skills/my-lib/` and target is `copilot`, rewrite to `root: .agents/skills/my-lib/`

This ensures each platform's managed section points to the correct platform-specific skill directory, including during migration from pre-platform-aware exports.

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

"**Context update prepared.{if multi-platform: ' (platform {i}/{total}: {platform})'}**

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

**Multi-platform behavior:** When processing multiple platforms, present all platforms' previews together before asking for a single confirmation. After confirmation, write all target files sequentially, verifying each one.

"**Targets:** {list all platform → target-file pairs}
**Ready to write changes to all targets?**"

Display: "**Select:** [C] Continue — write changes to all targets"

#### Menu Handling Logic:

- IF C: Write the changes to all target files (or single target), verify each write succeeded, then load, read entire file, then execute {nextStepFile}
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

**This section executes ONCE after all platform iterations complete** (outside the per-platform loop defined in section 3). Only platforms whose writes succeeded in section 9 are recorded.

1. Read `{skills_output_folder}/.export-manifest.json` (or start with `{"schema_version": "2", "exports": {}}` if it does not exist)
2. Ensure `schema_version` is `"2"` (if v1 was migrated in section 4a, the migrated structure is already in context)
3. Add or update the current skill's entry in v2 format:
   ```json
   "{skill-name}": {
     "active_version": "{version}",
     "versions": {
       "{version}": {
         "platforms": ["{successfully-written platforms}"],
         "last_exported": "{current-date}",
         "status": "active"
       }
     }
   }
   ```
   - `{version}` is the version from `{resolved_skill_package}/metadata.json`
   - Set `platforms` to only the platforms that were successfully written and verified in section 9
   - If the skill already has a manifest entry:
     - Set `active_version` to the current version
     - If the version already exists in `versions`, update its `platforms` (merge, deduplicate), `last_exported`, and set `status: "active"`
     - If this is a new version, add it to `versions` with `status: "active"` and set any previously-active version's status to `"archived"`
     - Preserve all other version entries in `versions` (do not delete archived versions)
4. Write the updated manifest to `{skills_output_folder}/.export-manifest.json`

**Dry-run mode:** Do NOT update the manifest. Display: "**[DRY RUN] Export manifest would be updated for {skill-name} on platform(s) {platform-list}.**"

**Error handling:** If manifest write fails, warn but do not fail the workflow — the managed section was already written successfully.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the user confirms changes by selecting 'C' (or auto-proceed in dry-run) and the write is verified will you load and read fully `{nextStepFile}` to execute the token report.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Managed section format loaded from {managedSectionData}
- Target file(s) correctly determined from platform flag or config.yaml ides list
- Multi-platform loop executed for all target_platforms
- Root paths rewritten per platform in managed section
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
