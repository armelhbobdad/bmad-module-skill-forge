---
nextStepFile: './step-07-generate-output.md'
stackSkillTemplate: 'assets/stack-skill-template.md'
---

# Step 6: Compile Stack Skill

## STEP GOAL:

Assemble the main SKILL.md by combining per-library extractions with the integration layer, and present for user review before writing output files.

## Rules

- Compile SKILL.md following the stack-skill-template structure — integration patterns go first (primary value)
- Do not write output files (Step 07)
- Present compiled content for user review

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

- `name`: lowercase alphanumeric + hyphens only, must match skill output directory name. Prefer gerund form (`processing-pdfs`) for clarity.
- `description`: non-empty, max 1024 chars, trigger-optimized for agent discovery. MUST use third-person voice ("Processes..." not "I can..." or "You can...").
- No other frontmatter fields — only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are permitted by spec

### 3. Compile Integration Layer

**This is the core value of the stack skill.** Compile in order:

**Zero-integration guard:** If the integration graph from step 05 has zero edges (no detected integration pairs), skip the integration layer compilation and note: "No integration patterns detected — stack skill will contain library summaries without an integration layer." Proceed directly to section 4 (Per-Library Sections).

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

For each confirmed library (ordered by integration connectivity, then import count — **in compose-mode**, order by integration connectivity, then skill confidence tier since import counts are not available):

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

(**in compose-mode**: replace the Imports column with Export Count from source skill metadata, since import counts are not available)

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
- **GATE [default: C]** — If `{headless_mode}`: auto-proceed with [C] Continue, log: "headless: auto-approve stack compilation"
- ONLY proceed to next step when user approves and selects 'C'

#### Menu Handling Logic:

- IF C: Store skill_content, then load, read entire file, then execute {nextStepFile}
- IF Any other: Process as feedback, adjust compilation, redisplay preview, then [Redisplay Menu Options](#8-present-menu-options)

