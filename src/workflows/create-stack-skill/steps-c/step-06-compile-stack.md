---
name: 'step-06-compile-stack'
description: 'Compile SKILL.md with integration layer and present for user review'

nextStepFile: './step-07-generate-output.md'
stackSkillTemplate: '../data/stack-skill-template.md'
---

# Step 6: Compile Stack Skill

## STEP GOAL:

Assemble the main SKILL.md by combining per-library extractions with the integration layer, and present for user review before writing output files.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are an integration architect operating in Ferris Architect mode
- ✅ The integration layer is the VALUE — not just concatenated library docs
- ✅ Zero hallucination — only include content backed by extraction evidence

### Step-Specific Rules:

- 🎯 Compile SKILL.md following the stack-skill-template structure
- 🚫 FORBIDDEN to write output files — that is step 07
- 💬 Present compiled content for user review (Gate 2)
- 🎯 Integration patterns go FIRST — they are the primary value

## EXECUTION PROTOCOLS:

- 🎯 Load stack-skill-template.md for section structure
- 💾 Store compiled skill_content as workflow state
- 📖 Wait for user review and approval before proceeding
- 🚫 FORBIDDEN to proceed without user confirming the compilation

## CONTEXT BOUNDARIES:

- From step 04: per_library_extractions[] with exports, patterns, confidence
- From step 05: integration_graph with pairs, types, hub libraries, cross-cutting patterns
- This step produces: skill_content (compiled SKILL.md ready for writing)
- User interaction: Gate 2 — compile checkpoint required

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Template Structure

Load `{stackSkillTemplate}` and prepare SKILL.md section structure.

### 2. Generate Frontmatter

The SKILL.md MUST begin with YAML frontmatter (agentskills.io compliance):

```yaml
---
name: {project_name}-stack
description: >
  Stack skill for {project_name} — {lib_count} libraries with
  {integration_count} integration patterns. Use when working with
  this project's technology stack. NOT for: individual library usage
  outside this project's conventions.
---
```

**Frontmatter rules:**

- `name`: lowercase alphanumeric + hyphens only, must match skill output directory name
- `description`: non-empty, max 1024 chars, trigger-optimized for agent discovery
- No other frontmatter fields — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted by spec

### 3. Compile Integration Layer

**This is the core value of the stack skill.** Compile in order:

**Cross-cutting patterns** (if any):
- Patterns spanning 3+ libraries
- Middleware chains, shared configuration, common architectural patterns

**Library pair integrations:**
- For each detected integration pair from step 05:
  - Type classification
  - Pattern description with file:line citations
  - Key files demonstrating the integration
  - Confidence tier label

**Hub library connections:**
- For each hub library (3+ connections):
  - Role in the stack architecture
  - How it connects to partner libraries

### 4. Compile Per-Library Sections

For each confirmed library (ordered by integration connectivity, then import count):

- Role in stack (one-line description)
- Key exports used in this project
- Usage patterns from extraction
- Confidence tier label
- Link to reference file: `./references/{library}.md`

### 5. Compile Project Conventions

Extract project-specific conventions from the extractions:
- Common initialization patterns
- Error handling approaches across libraries
- Configuration conventions
- Import organization patterns

### 6. Compile Library Reference Index

Create the reference index table:

| Library | Imports | Key Exports | Confidence | Reference |
|---------|---------|-------------|------------|-----------|
| ... | ... | ... | ... | ... |

### 7. Present Compiled SKILL.md Preview

"**Stack skill compilation complete. Please review:**

---

{Display full compiled SKILL.md content}

---

**Compilation stats:**
- **Libraries:** {count}
- **Integration pairs:** {count}
- **Cross-cutting patterns:** {count}
- **Confidence:** T1: {count}, T1-low: {count}, T2: {count}

**Please review the integration layer and per-library sections.**
- Does the integration layer capture how your libraries connect?
- Are the per-library summaries accurate?
- Any sections to adjust before writing output?"

### 8. Present MENU OPTIONS

Display: **Select:** [C] Continue to Output Generation

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting compilation
- ONLY proceed to next step when user approves and selects 'C'

#### Menu Handling Logic:

- IF C: Store skill_content, then load, read entire file, then execute {nextStepFile}
- IF Any other: Process as feedback, adjust compilation, redisplay preview, then [Redisplay Menu Options](#8-present-menu-options)

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- SKILL.md follows stack-skill-template structure
- Integration layer presented FIRST (primary value)
- All content includes confidence tier labels
- Per-library sections ordered by connectivity
- User reviewed and approved compilation
- skill_content stored for step 07

### ❌ SYSTEM FAILURE:

- Integration layer missing or buried below library listings
- Content without confidence tier labels
- Proceeding without user review (Gate 2)
- Writing files in this step (step 07's job)
- Fabricating integration patterns not from step 05

**Master Rule:** Integration layer is the value. Present it first, get user approval before writing.
