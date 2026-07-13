---
nextStepFile: 'report.md'
# {arch_project_name} resolved in init.md (arch-doc frontmatter project_name, else config project_name).
outputFile: '{outputFolderPath}/refined-architecture-{arch_project_name}.md'
---

<!-- Config: communicate in {communication_language}. Compile the refined architecture document in {document_output_language}. -->

# Step 5: Compile Refined Architecture

## STEP GOAL:

Produce the refined architecture document by starting with the original as a base, adding gap-fill subsections, issue callout blocks, and improvement suggestions. Append a Refinement Summary. Present for user review before finalizing.

## Rules

- Do not discover new gaps, issues, or improvements — use only what Steps 02-04 produced
- Do not delete, reword, or rearrange original architecture content
- Present compiled document for user review (gate checkpoint)

## MANDATORY SEQUENCE

### 1. Prepare the Original as Base

Load the complete original architecture document.

This is the base. Every line of the original appears in the refined document unmodified — the workflow only adds annotations and subsections; dropping or rewording original content silently discards the user's architecture.

**Context recovery check:** If gap, issue, or improvement findings from Steps 02-04 are not available in context (e.g., due to context degradation in long runs), attempt to read the durability state from `{forge_data_folder}/ra-state-{project_name}.md`. Parse the `<!-- [RA-GAPS] -->`, `<!-- [RA-ISSUES] -->`, and `<!-- [RA-IMPROVEMENTS] -->` comment blocks to recover the complete formatted findings (each block contains full citation text with evidence, not just counts). If a section is still missing or contains only summary counts after recovery, HALT (exit code 8, `halt_reason: "recovery-failed"`): "⚠️ Context for the [Gaps|Issues|Improvements] analysis was lost and the durability state is insufficient to reconstruct findings. Re-run [RA] from the beginning — step 01 will reset the state file, then steps 02-04 will rebuild all findings." In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" with `refined_path: null`.

### 2. Insert Gap-Fill Subsections

For each gap finding from Step 02:

**Locate the most relevant section** in the original architecture where this integration would logically belong.

**Insert a gap-fill subsection** one heading level deeper than the parent section:

```markdown
#### RA: {Library A} <-> {Library B} Integration Path

> [!NOTE] **Gap Identified by Refine Architecture**
> This integration path was not documented in the original architecture but is supported by skill API evidence.

{Gap description with full evidence citation from Step 02}

**Proposed Integration:**
{Suggested architecture content describing how the libraries connect}
```

If no clear parent section exists, collect orphan gaps into a new section: "## RA: Additional Integration Paths"

### 3. Insert Issue Annotations

For each issue finding from Step 03:

**Locate the section** containing the contradicted claim.

**Insert an issue callout block** immediately after the contradicted text:

```markdown
> [!WARNING] **Issue Detected by Refine Architecture** ({severity})
> Architecture states: "{quoted claim}"
> Skill reality: {contradicting evidence from skill}
> {IF VS report}: VS verdict: {verdict} for {pair}
>
> **Suggested Correction:** {specific correction with API evidence}
```

**Placement priority:** Place each issue callout immediately after the contradicted text in its original location. If the contradicted claim is inside a Markdown list item, code block, or table row where inserting a callout block would break syntax, place the callout immediately after the enclosing block instead. If the contradicted claim cannot be precisely located, collect into "## RA: Additional Issues Detected" at the end of the document, ordered by severity (Critical first, then Major, then Minor).

### 4. Insert Improvement Suggestions

For each improvement finding from Step 04:

**Locate the section** where the library is discussed.

**Insert an improvement subsection** one heading level deeper:

```markdown
#### RA: Enhancement — {Improvement Title}

> [!TIP] **Improvement Suggested by Refine Architecture** ({value} value)
> {skill_name} provides `{api}` which is not currently leveraged.

{Full improvement description with evidence citation from Step 04}

**How to Incorporate:**
{Specific suggestion for updating the architecture}
```

**Order by value:** High value improvements first, then Medium, then Low.

**Placement fallback:** If the library's only architecture mention is inside a table, code block, or Mermaid diagram where inserting a subsection would break syntax, collect into `## RA: Additional Improvements Suggested` at the end of the document.

### 5. Add Refinement Summary Section

Append a `## Refinement Summary` section containing:

- **Header:** "Produced by: Refine Architecture workflow using {skill_count} skills" and date
- **Changes Made table** with the following rows:

| Category | Count | Breakdown |
|----------|-------|-----------|
| Gaps Filled | {gap_count} | — |
| Issues Flagged | {issue_count} | Critical: {critical_count}, Major: {major_count}, Minor: {minor_count} |
| Improvements Suggested | {improvement_count} | High: {high_count}, Medium: {medium_count}, Low: {low_count} |
| Skills Used as Evidence | {skill_count} | — |
- **Evidence Sources table:** Each skill name and how many refinements cite it
- **Next Steps:** Review `[!WARNING]` issues, `[!NOTE]` gaps, `[!TIP]` improvements; then run **[SS] Stack Skill** to compose your individual skills into a unified stack skill, providing this refined architecture doc when prompted

### 6. Write the Refined Document

Write the complete refined architecture to `{outputFile}`.

On any write failure (read-only mount, disk full, permissions denied): HALT (exit code 4, `halt_reason: "write-failed"`) with the captured error. In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" with `refined_path: null`. The On-Activation §5 write probe should have caught an unwritable output folder earlier — if it surfaces here, the filesystem state changed mid-workflow.

### 7. Present Compiled Document for Review

"**Refined architecture compiled. Please review:**

---

{Display the Refinement Summary section only — not the full document}

---

**The full refined document has been written to:** `{outputFile}`

Please review the refinements:
- {gap_count} gap-fill subsections added
- {issue_count} issue annotations inserted
- {improvement_count} improvement suggestions included
- Original architecture content preserved in full

**Does the refinement look correct?**"

### 8. Present MENU OPTIONS

Display: **Select:** [C] Continue to Final Report | [X] Cancel

#### GATE [default: C]

This is a review gate: halt for the user's decision and do not chain onward until they approve — an unreviewed compile ships un-vetted refinements. Headless auto-selects [C] (log: "headless: auto-approve compiled architecture").

#### Menu Handling Logic:

- IF C: Load, read entire file, then execute {nextStepFile}
- IF cancel / exit / [X] / q / :q: HALT (exit code 6, `halt_reason: "user-cancelled"`) — display "Cancelled — refinement not finalized." In headless, emit the error envelope per SKILL.md "Result Contract (Headless)" with `refined_path: null`. These global cancel tokens pre-empt the feedback branch below.
- IF Any other: Process as feedback, adjust specific refinements in the document, rewrite {outputFile}, redisplay preview, then [Redisplay Menu Options](#8-present-menu-options)

