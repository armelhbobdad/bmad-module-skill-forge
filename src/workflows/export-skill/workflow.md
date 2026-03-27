---
name: export-skill
description: Package for distribution + platform-aware context injection
web_bundle: true
installed_path: '{project-root}/_bmad/skf/workflows/skillforge/export-skill'
---

# Export Skill

**Goal:** Package a completed skill as an agentskills.io-compliant package, generate context snippets, and update the managed section in CLAUDE.md/.cursorrules/AGENTS.md for platform-aware context injection.

**Your Role:** In addition to your name, communication_style, and persona, you are also a delivery and packaging specialist collaborating with a skill developer. This is a partnership, not a client-vendor relationship. You bring expertise in skill packaging, ecosystem compliance, and context injection patterns, while the user brings their completed skill and distribution requirements. Work together as equals.

**Meta-Context:** This workflow is the sole publishing gate for skills (ADR-K). Create-skill and update-skill produce draft artifacts — only export-skill writes to CLAUDE.md/AGENTS.md and prepares packages for distribution. This prevents half-baked snippets from entering the agent's passive context.

---

## WORKFLOW ARCHITECTURE

### Core Principles

- **Micro-file Design**: Each step of the overall goal is a self contained instruction file that you will adhere to 1 file as directed at a time
- **Just-In-Time Loading**: Only 1 current step file will be loaded, read, and executed to completion - never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **Action-Based Output**: This workflow performs file operations (writes, updates) rather than building a progressive document

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
- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`

---

## INITIALIZATION SEQUENCE

### 1. Module Configuration Loading

Load and read full config from {project-root}/_bmad/skf/config.yaml and resolve:

- `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
- `skills_output_folder`, `forge_data_folder`, `sidecar_path`

### 2. First Step Execution

Load, read the full file and then execute `./steps-c/step-01-load-skill.md` to begin the workflow.
