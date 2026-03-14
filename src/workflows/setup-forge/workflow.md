---
name: setup-forge
description: Initialize forge environment, detect tools, set tier, auto-index project
web_bundle: true
installed_path: '{project-root}/_bmad/skf/workflows/skillforge/setup-forge'
---

# Setup Forge

**Goal:** Initialize the forge environment by detecting available tools, determining the capability tier (Quick/Forge/Deep), writing persistent configuration, and optionally indexing the project for deep search.

**Your Role:** You are a system executor performing environment resolution. This is a fully autonomous workflow — no user interaction is required during execution. Run each step in sequence, write configuration files, and report results at completion.

## WORKFLOW ARCHITECTURE

### Core Principles

- **Micro-file Design**: Each step of the overall goal is a self contained instruction file that you will adhere too 1 file as directed at a time
- **Just-In-Time Loading**: Only 1 current step file will be loaded, read, and executed to completion - never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **Fully Autonomous**: All steps auto-proceed with no user interaction until the final report

### Step Processing Rules

1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute all numbered sections in order, never deviate
3. **AUTO-PROCEED**: Each step proceeds to the next automatically after completion
4. **LOAD NEXT**: When directed, load, read entire file, then execute the next step file

### Critical Rules (NO EXCEPTIONS)

- 🛑 **NEVER** load multiple step files simultaneously
- 📖 **ALWAYS** read entire step file before execution
- 🚫 **NEVER** skip steps or optimize the sequence
- 🎯 **ALWAYS** follow the exact instructions in the step file
- 📋 **NEVER** create mental todo lists from future steps

---

## INITIALIZATION SEQUENCE

### 1. Module Configuration Loading

Load and read full config from {project-root}/_bmad/skf/config.yaml and resolve:

- `project_name`, `output_folder`, `user_name`, `communication_language`, `document_output_language`

### 2. First Step Execution

Load, read the full file and then execute ./steps-c/step-01-detect-and-tier.md to begin the workflow.
