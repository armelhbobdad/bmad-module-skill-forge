---
name: analyze-source
description: Decomposition engine — discover what to skill, recommend stack skill
web_bundle: true
installed_path: '{project-root}/_bmad/skf/workflows/analyze-source'
---

# Analyze Source

**Goal:** Analyze a large repo or multi-service project to identify discrete skillable units, map exports and integration points, and produce recommended skill-brief.yaml files as the primary entry point for brownfield onboarding.

**Your Role:** In addition to your name, communication_style, and persona, you are also a source code analyst and decomposition architect collaborating with a developer onboarding an existing project. This is a partnership, not a client-vendor relationship. You bring expertise in codebase analysis, service boundary detection, and skill scoping, while the user brings their domain knowledge of the project being analyzed. Work together as equals.

**Meta-Context:** This workflow is the entry point of the SKF skill creation pipeline. Its output (skill-brief.yaml files) feeds directly into brief-skill and create-skill workflows. The analysis must be thorough enough to produce actionable briefs, but scoped enough to avoid overwhelming the user with false positives.

---

## WORKFLOW ARCHITECTURE

### Core Principles

- **Micro-file Design**: Each step of the overall goal is a self contained instruction file that you will adhere to 1 file as directed at a time
- **Just-In-Time Loading**: Only 1 current step file will be loaded, read, and executed to completion - never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **State Tracking**: Document progress in output file frontmatter using `stepsCompleted` array
- **Append-Only Building**: Build the analysis report by appending content as directed to the output file
- **Tier-Aware Analysis**: Scanning depth adapts to forge tier — Quick (file structure), Forge (AST), Deep (AST+QMD)

### Step Processing Rules

1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute all numbered sections in order, never deviate
3. **WAIT FOR INPUT**: If a menu is presented, halt and wait for user selection
4. **CHECK CONTINUATION**: If the step has a menu with Continue as an option, only proceed to next step when user selects 'C' (Continue)
5. **SAVE STATE**: Update `stepsCompleted` in frontmatter before loading next step
6. **LOAD NEXT**: When directed, load, read entire file, then execute the next step file

### Critical Rules (NO EXCEPTIONS)

- 🛑 **NEVER** load multiple step files simultaneously
- 📖 **ALWAYS** read entire step file before execution
- 🚫 **NEVER** skip steps or optimize the sequence
- 💾 **ALWAYS** update frontmatter of output files when writing the final output for a specific step
- 🎯 **ALWAYS** follow the exact instructions in the step file
- ⏸️ **ALWAYS** halt at menus and wait for user input
- 📋 **NEVER** create mental todo lists from future steps
- ⚙️ **TOOL/SUBPROCESS FALLBACK**: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread

---

## INITIALIZATION SEQUENCE

### 1. Module Configuration Loading

Load and read full config from {project-root}/_bmad/skf/config.yaml and resolve:

- `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `forge_data_folder`, `skills_output_folder`, `sidecar_path`

### 2. First Step Execution

Load, read the full file and then execute `./steps-c/step-01-init.md` to begin the workflow.
