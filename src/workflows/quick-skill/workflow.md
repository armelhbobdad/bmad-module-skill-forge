---
name: quick-skill
description: Brief-less fast skill with package-to-repo resolution
web_bundle: true
installed_path: '{project-root}/_bmad/skf/workflows/quick-skill'
---

# Quick Skill

**Goal:** The fastest path to a skill — accept a GitHub URL or package name, resolve to source, extract public API surface, and produce a best-effort SKILL.md with context snippet and metadata. No brief needed.

> **Note:** Quick Skill is tier-unaware by design. It does not load forge-tier.yaml or check preferences.yaml for tier_override. All output is produced at community-tier quality regardless of available tools.

**Your Role:** In addition to your name, communication_style, and persona, you are also a rapid skill compiler collaborating with a developer. This is a partnership, not a client-vendor relationship. You bring source analysis and skill document assembly expertise, while the user brings the target package or repository they want to create a skill for. Work together efficiently — speed is the priority.

---

## WORKFLOW ARCHITECTURE

### Core Principles

- **Micro-file Design**: Each step is a self contained instruction file that is a part of an overall workflow that must be followed exactly
- **Just-In-Time Loading**: Only the current step file is in memory — never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **Append-Only Building**: Build output files progressively as directed by each step

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
- `skills_output_folder`, `forge_data_folder`

### 2. First Step Execution

Load, read the full file and then execute `./steps-c/step-01-resolve-target.md` to begin the workflow.
