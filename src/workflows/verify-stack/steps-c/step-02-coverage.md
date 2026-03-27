---
name: 'step-02-coverage'
description: 'Pass 1 — check that a generated skill exists for every technology referenced in the architecture document'

nextStepFile: './step-03-integrations.md'
coveragePatternsData: '../data/coverage-patterns.md'
outputFile: '{forge_data_folder}/feasibility-report-{project_name}.md'
---

# Step 2: Technology Coverage Analysis

## STEP GOAL:

Verify that a generated skill exists for every technology, library, or framework referenced in the architecture document. Produce a coverage matrix showing which technologies are covered and which are missing. Detect extra skills not referenced in the architecture.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a stack verification analyst performing coverage analysis
- ✅ Every technology reference must trace to actual text in the architecture document
- ✅ Matching must be precise — do not guess or infer technologies not explicitly mentioned

### Step-Specific Rules:

- 🎯 Focus ONLY on technology-to-skill coverage mapping
- 🚫 FORBIDDEN to analyze API surfaces or integration compatibility — that is Step 03
- 🚫 FORBIDDEN to evaluate requirements — that is Step 04
- 💬 Coverage verdicts must be binary: Covered or Missing — no ambiguity

## EXECUTION PROTOCOLS:

- 🎯 Extract technology references from architecture document using {coveragePatternsData}
- 💾 Build and display coverage matrix with Covered/Missing verdicts
- 📖 Append Coverage Matrix section to {outputFile}
- 🚫 Only coverage mapping — no integration analysis, no requirements checking

## CONTEXT BOUNDARIES:

- Available: Architecture document content, skill inventory from Step 01, coverage patterns data
- Focus: Technology-to-skill matching only
- Limits: Do not read SKILL.md in detail — use metadata.json for name and source_repo matching only
- Dependencies: Step 01 must have loaded skill inventory and validated architecture document

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Coverage Patterns

Load `{coveragePatternsData}` for detection rules.

Extract: technology name patterns, section heading indicators, common aliases, and framework-to-library mappings.

### 2. Extract Technology References

Parse the architecture document for technology, library, and framework names.

**Detection methods (apply in order):**

**Section-based detection:**
- Identify section headings that indicate technology listings (e.g., "Tech Stack", "Dependencies", "Technologies", "Libraries", layer-specific headings)
- Extract technology names listed under these headings

**Direct name matching:**
- Scan the full document for names that match loaded skill names (case-insensitive)
- Apply alias resolution from {coveragePatternsData} (e.g., "React" matches "react", "PostgreSQL" matches "postgres")

**Contextual detection:**
- Identify technology names mentioned in prose alongside architectural descriptions
- Look for version-pinned references (e.g., "Express v4", "Tailwind CSS 3.x")

**Build a deduplicated list** of all referenced technologies with the document section where each was found.

### 3. Cross-Reference Against Skills

For each referenced technology in the list:

**Check if a matching skill exists** in the skill inventory from Step 01.
- Match by skill name (case-insensitive)
- Match by alias from {coveragePatternsData}
- Match by `source_repo` or `source_root` field in metadata.json if skill name differs from technology name

**Assign verdict:**
- **Covered** — a matching skill exists in the inventory
- **Missing** — no matching skill found

Build the coverage matrix as a structured table.

### 4. Detect Extra Skills

Check if any skills in the inventory are NOT referenced in the architecture document.

**For each extra skill:**
- Mark as **Extra** (informational — not an error)
- Note: "Skill `{skill_name}` exists but is not referenced in the architecture document"

Extra skills are informational only. They do not affect the coverage verdict.

### 5. Display Coverage Results

"**Pass 1: Technology Coverage**

| Technology | Source Section | Skill Match | Verdict |
|------------|---------------|-------------|---------|
| {tech_name} | {section_heading} | {skill_name or '—'} | {Covered / Missing} |

**Coverage: {covered_count}/{total_count} ({percentage}%)**

{IF 100% coverage AND no Extra skills:}
**All referenced technologies have a matching skill. No extra skills detected.**

{IF any Missing:}
**Missing Skills — Action Required:**
{For each missing technology:}
- `{tech_name}` → Run **[CS] Create Skill** or **[QS] Quick Skill** for `{tech_name}`, then re-run **[VS]**

{IF any Extra:}
**Extra Skills (informational):**
{For each extra skill:}
- `{skill_name}` — not referenced in architecture document"

### 6. Append to Report

Write the **Coverage Matrix** section to `{outputFile}`:
- Include the full coverage table
- Include coverage percentage
- Include missing skill recommendations
- Include extra skills list
- Update frontmatter: append `'step-02-coverage'` to `stepsCompleted`, set `coverage_percentage`

### 7. Auto-Proceed to Next Step

{IF coverage_percentage is 0%:}
"**⚠️ 0% coverage — no matching skills found for any referenced technology.** All subsequent analysis (integration, requirements) will be vacuous and produce empty tables.

**Recommended:** Generate skills with [CS] or [QS] for your architecture technologies, then re-run [VS].

**Select:** [X] Halt workflow (recommended) | [C] Continue anyway"

- IF X: "**Workflow halted.** Generate skills and re-run [VS] when ready." — END workflow
- IF C: "**Continuing with 0% coverage — results will be limited.**"

  Load, read the full file and then execute `{nextStepFile}`.

{IF coverage_percentage is NOT 0%:}
"**Proceeding to integration analysis...**"

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Coverage patterns loaded from {coveragePatternsData}
- All technology references extracted from architecture document with section citations
- Every referenced technology cross-referenced against skill inventory
- Coverage matrix displayed with binary Covered/Missing verdicts
- Extra skills detected and reported as informational
- Missing skills have actionable recommendations (run [CS] or [QS])
- Coverage Matrix section appended to {outputFile}
- Auto-proceeded to step 03

### ❌ SYSTEM FAILURE:

- Inventing technologies not mentioned in the architecture document
- Ambiguous verdicts (anything other than Covered or Missing)
- Analyzing API surfaces or skill content in detail (that is Step 03)
- Not providing actionable recommendations for missing skills
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
