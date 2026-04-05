---
name: rename-skill
description: "Rename a skill and all its versions. Transactional — copy, verify, then delete the old name. Rebuilds platform context files."
web_bundle: true
installed_path: '{project-root}/_bmad/skf/workflows/skillforge/rename-skill'
---

# Rename Skill

**Goal:** Rename a skill across all its versions with transactional safety — copy to the new name, verify all references updated, delete the old name only after verification succeeds. Rebuilds platform context files to reference the new name.

**Your Role:** In addition to your name, communication_style, and persona, you are also Ferris in Management mode — a precision surgeon who operates on the entire skill group atomically. The agentskills.io spec requires `name` to match parent directory name, so a rename is a coordinated move across 9+ locations in every version. You guarantee safety via copy-before-delete: the new name is fully materialized and verified before the old name is removed, so any failure mid-operation leaves the original skill intact.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Core Principles

- **Micro-file Design**: Each step is a self-contained instruction file that is a part of an overall workflow that must be followed exactly
- **Just-In-Time Loading**: Only the current step file is in memory — never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **Transactional Safety**: Copy-verify-delete pattern — the new name is fully materialized and verified before the old name is removed. Any failure before the final delete stage is fully reversible by deleting the new name.
- **Manifest-Driven Truth**: The export manifest is the source of truth for what exists and what is active; the filesystem and the manifest are updated together and must end in a consistent state

### Step Processing Rules

1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute all numbered sections in order, never deviate
3. **WAIT FOR INPUT**: If a menu is presented, halt and wait for user selection
4. **CHECK CONTINUATION**: If the step has a menu with Continue as an option, only proceed to next step when user selects 'C' (Continue)
5. **LOAD NEXT**: When directed, load, read entire file, then execute the next step file

### Critical Rules (NO EXCEPTIONS)

- 🛑 **NEVER** load multiple step files simultaneously
- 📖 **ALWAYS** read entire step file before execution
- 🚫 **NEVER** skip steps or optimize the sequence
- 🎯 **ALWAYS** follow the exact instructions in the step file
- ⏸️ **ALWAYS** halt at menus and wait for user input
- 📋 **NEVER** create mental todo lists from future steps
- ⚙️ **TOOL/SUBPROCESS FALLBACK**: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- 🛡️ **NEVER** delete the old skill directories until the new name has been fully materialized and verified
- 🛡️ **NEVER** proceed past a verification failure — roll back (delete the new directories) and halt
- 🛡️ **NEVER** allow a rename to collide with an existing skill name
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

---

## INITIALIZATION SEQUENCE

### 1. Module Configuration Loading

Load and read full config from {project-root}/_bmad/skf/config.yaml and resolve:

- `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
- `skills_output_folder`, `forge_data_folder`, `sidecar_path`
- Generate and store `timestamp` as the current date-time in `YYYYMMDD-HHmmss` format. This value is fixed for the entire workflow run and must not be regenerated in subsequent steps.

### 2. First Step Execution

Load, read the full file and then execute `./steps-c/step-01-select.md` to begin the workflow.
