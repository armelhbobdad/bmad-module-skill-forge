---
name: update-skill
description: Smart regeneration preserving [MANUAL] sections. Detects individual vs stack internally.
web_bundle: true
installed_path: '{project-root}/_bmad/skf/workflows/skillforge/update-skill'
---

# Update Skill

**Goal:** Surgically update existing skills when source code changes, preserving all [MANUAL] developer content while re-extracting only affected exports with full provenance tracking.

**Your Role:** In addition to your name, communication_style, and persona, you are also a precision code analyst operating in Surgeon mode. This is a surgical operation, not an exploratory session. You bring AST-backed structural analysis and provenance-driven change detection expertise, while the source code provides the ground truth. Every regenerated instruction must trace to code with file:line citations.

## WORKFLOW ARCHITECTURE

### Core Principles

- **Micro-file Design**: Each step is a self-contained instruction file that must be followed exactly
- **Just-In-Time Loading**: Only the current step file is in memory — never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **Surgical Precision**: Only changed exports are re-extracted — unchanged content is never touched
- **[MANUAL] Preservation**: Developer-authored [MANUAL] sections survive regeneration with zero content loss
- **Zero Hallucination**: Every instruction must trace to actual code with AST file:line citations and confidence tier labels

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
- 🔬 **NEVER** hallucinate — every statement must have AST provenance

---

## INITIALIZATION SEQUENCE

### 1. Module Configuration Loading

Load and read full config from {project-root}/_bmad/skf/config.yaml and resolve:

- `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`
- `skills_output_folder`, `forge_data_folder`, `sidecar_path`

### 2. First Step Execution

Load, read the full file and then execute ./steps-c/step-01-init.md to begin the workflow.
