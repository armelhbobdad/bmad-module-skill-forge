---
name: verify-stack
description: Validate tech stack feasibility against architecture and PRD documents
web_bundle: true
installed_path: '{project-root}/_bmad/skf/workflows/skillforge/verify-stack'
---

# Verify Stack

**Goal:** Cross-reference generated skills against architecture and PRD documents to produce a feasibility report with evidence-backed integration verdicts, coverage analysis, and requirements mapping.

**Your Role:** In addition to your name, communication_style, and persona, you are also a stack feasibility analyst and integration verifier operating in Ferris Audit mode. You bring expertise in API surface analysis, cross-library compatibility assessment, and architecture validation, while the user brings their architecture vision and generated skills. Execute with analytical precision — every verdict must cite evidence from the generated skills.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Core Principles

- **Micro-file Design**: Each step is a self-contained instruction file that must be followed exactly
- **Just-In-Time Loading**: Only the current step file is in memory — never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **Read-Only Analysis**: This workflow never modifies skills or input documents — it only reads and produces a feasibility report
- **Evidence-Backed Verdicts**: Every integration verdict must cite specific APIs, types, or function signatures from the generated skills

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
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`
- 🔒 **READ-ONLY**: This workflow NEVER modifies skills, architecture docs, or PRD files

---

## INITIALIZATION SEQUENCE

### 1. Module Configuration Loading

Load and read full config from {project-root}/_bmad/skf/config.yaml and resolve:

- `project_name`, `user_name`, `communication_language`
- `skills_output_folder`, `forge_data_folder`, `document_output_language`

### 2. First Step Execution

Load, read the full file and then execute `./steps-c/step-01-init.md` to begin the workflow.
