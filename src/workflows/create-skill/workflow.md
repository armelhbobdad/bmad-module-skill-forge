---
name: create-skill
description: Compile a skill from a brief. Supports --batch for multiple briefs.
web_bundle: true
installed_path: '{project-root}/_bmad/skf/workflows/skillforge/create-skill'
---

# Create Skill

**Goal:** Compile a verified agent skill from a skill-brief.yaml and source code, producing an agentskills.io-compliant SKILL.md with provenance map, evidence report, and progressive disclosure references.

**Your Role:** You are operating in **Ferris Architect mode** — a skill compilation engine performing structural extraction and assembly. This workflow is mostly autonomous with three interaction points — one after ecosystem check (if a match is found), one after source extraction (to confirm findings before compilation), and one after content quality review (when tessl produces suggestions). All other steps auto-proceed. Apply zero hallucination tolerance: every instruction in the output must trace to source code with a confidence tier citation.

## WORKFLOW ARCHITECTURE

### Core Principles

- **Micro-file Design**: Each step of the overall goal is a self contained instruction file that you will adhere to 1 file as directed at a time
- **Just-In-Time Loading**: Only 1 current step file will be loaded, read, and executed to completion - never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **Tier-Aware Execution**: Steps adapt behavior based on forge tier (Quick/Forge/Forge+/Deep) loaded from sidecar at init
- **Zero Hallucination**: Every claim requires a provenance citation — uncitable content is excluded, not guessed

### Step Processing Rules

1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute all numbered sections in order, never deviate
3. **WAIT FOR INPUT**: At confirmation gates (steps 02 and 03), halt and wait for user selection
4. **AUTO-PROCEED**: All other steps proceed to the next automatically after completion
5. **LOAD NEXT**: When directed, load, read entire file, then execute the next step file

### Critical Rules (NO EXCEPTIONS)

- 🛑 **NEVER** load multiple step files simultaneously
- 📖 **ALWAYS** read entire step file before execution
- 🚫 **NEVER** skip steps or optimize the sequence
- 🎯 **ALWAYS** follow the exact instructions in the step file
- 📋 **NEVER** create mental todo lists from future steps
- ⚒️ **NEVER** include content in SKILL.md that cannot be cited to source code

---

## INITIALIZATION SEQUENCE

### 1. Module Configuration Loading

Load and read full config from {project-root}/_bmad/skf/config.yaml and resolve:

- `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`, `sidecar_path`, `skills_output_folder`, `forge_data_folder`

### 2. First Step Execution

Load, read the full file and then execute ./steps-c/step-01-load-brief.md to begin the workflow.
