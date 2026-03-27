---
name: 'step-02-gap-analysis'
description: 'Find undocumented integration paths that the architecture does not describe but skill APIs suggest'

nextStepFile: './step-03-issue-detection.md'
refinementRulesData: '../data/refinement-rules.md'
---

# Step 2: Gap Analysis

## STEP GOAL:

Find undocumented integration paths — library pairs that have compatible APIs (from the generated skills) but are not described in the architecture document. For each gap, document what APIs connect and propose an architecture section describing the integration.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are an architecture refinement analyst performing gap detection
- ✅ Every gap must cite specific APIs from the generated skills — no speculation
- ✅ Apply the gap detection rules from {refinementRulesData} strictly

### Step-Specific Rules:

- 🎯 Focus ONLY on undocumented integration paths (gaps)
- 🚫 FORBIDDEN to detect contradictions or issues — that is Step 03
- 🚫 FORBIDDEN to suggest capability expansions or improvements — that is Step 04
- 💬 Every gap MUST include evidence citations from actual skill content

## EXECUTION PROTOCOLS:

- Load refinement rules for gap detection criteria
- Extract integration claims from architecture document using prose co-mention analysis
- Generate all possible library pairs and cross-reference against architecture
- Append gap analysis findings as workflow state for Step 05
- Only gap detection — no issue detection, no improvement suggestions

## CONTEXT BOUNDARIES:

- Available: Architecture document content, skill inventory from Step 01, SKILL.md and metadata.json files, refinement rules
- Focus: Finding library pairs with compatible APIs that the architecture does not describe
- Limits: Only detect gaps — do not flag issues or suggest improvements
- Dependencies: Step 01 must have loaded skill inventory and validated architecture document

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Reference Refinement Rules

Use the refinement rules loaded in Step 01 from `{refinementRulesData}`. If not available in context, reload from `{refinementRulesData}`.

Extract: gap classification (Missing Integration Path, Undocumented Data Flow, Absent Bridge Layer), detection method, and citation format.

### 2. Extract Integration Claims from Architecture

Parse the architecture document for statements describing two or more technologies working together.

**Detection method — prose-based co-mention analysis:**
- Identify sentences or paragraphs where two or more technology names appear together
- Look for integration verbs: "connects to", "communicates with", "wraps", "extends", "consumes", "produces", "bridges", "integrates with", "sits between", "feeds into", "receives from"
- Look for data flow descriptions: "{A} sends data to {B}", "{A} results are consumed by {B}"
- Look for layer boundary descriptions: "{A} at the API layer connects to {B} at the data layer"

**CRITICAL:** Do NOT parse Mermaid diagram syntax. Use only prose text for co-mention detection.

**Mermaid Limitation Warning:** If `` ```mermaid `` blocks are present in the architecture document, inform the user: "Integration paths documented exclusively in Mermaid diagrams are excluded from co-mention analysis and may appear as false-positive gaps. Consider adding prose descriptions for diagram-only integration paths." Display this warning informatively and immediately continue — this does not halt or modify the analysis sequence.

**Build documented pairs list:**
- Each pair: `{library_a, library_b, architectural_context}`
- `architectural_context`: the quoted text or paraphrased description of their relationship

### 3. Generate All Possible Library Pairs

From the skill inventory, generate all unique combinations of library pairs.

For N skills, this produces N*(N-1)/2 unique pairs.

### 4. Load Skill API Surfaces for Cross-Reference

For each library in the skill inventory, load the skill artifacts:

**From SKILL.md, extract:**
- Exported functions and their signatures
- Exported types, interfaces, and classes
- Protocol indicators (HTTP, gRPC, WebSocket, message queue, file I/O, IPC)
- Data format indicators (JSON, protobuf, CSV, binary, streaming)

**From metadata.json, extract:**
- `language` — primary programming language
- `exports` — export count and names

### 5. Cross-Reference: Identify Gaps

For each possible library pair NOT already documented in the architecture:

**Check API compatibility:**
- Does Library A export types or data that Library B can consume?
- Do both libraries share a compatible protocol or data format?
- Are they in the same language or is there a bridge mechanism available?

**If compatible APIs exist but NO architecture mention:**
- Classify the gap type (Missing Integration Path, Undocumented Data Flow, or Absent Bridge Layer)
- Document the connecting APIs from both skills
- Propose a brief architecture section describing the integration

**Apply the citation format from {refinementRulesData}:**
```
**[GAP]**: {description}

Evidence:
- {skill_a} exports: `{function}({params}) -> {return_type}`
- {skill_b} accepts: `{function}({params})`
- Compatibility: {explanation}

Suggestion: {proposed architecture section content}
```

**If no compatible APIs:** Skip this pair — not all pairs need to integrate.

### 6. Display Gap Analysis Results

"**Pass 1: Gap Analysis — Undocumented Integration Paths**

**Gaps Found:** {count}

{IF gaps found:}
| # | Library A | Library B | Gap Type | Connecting APIs |
|---|-----------|-----------|----------|-----------------|
| {n} | {lib_a} | {lib_b} | {gap_type} | {brief API description} |

{For each gap, display the full citation with evidence and suggestion}

{IF no gaps found AND N > 1:}
**No undocumented integration paths detected.** The architecture document covers all compatible library pairs.

{IF no gaps found AND N == 1:}
**⚠️ Gap analysis skipped — only 1 skill loaded.** Pairwise integration analysis requires at least 2 skills. If the architecture references multiple libraries, those without a matching skill are invisible to gap analysis. **Recommendation:** Generate skills for all architecture libraries with [CS] or [QS] before running [RA] for comprehensive gap detection.

**Proceeding to issue detection (still produces value with 1 skill)...**"

Store all gap findings as workflow state for Step 05. To ensure durability across long runs, also append a `<!-- [RA-GAPS] ... -->` comment block to `{forge_data_folder}/ra-state-{project_name}.md` containing the **complete formatted gap findings** (full citation blocks with evidence and suggestions, not just counts) — Step 05 can read this back if context degrades. **Do NOT write to `{output_folder}/refined-architecture-{project_name}.md` — that file is created only in step-05.**

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Refinement rules loaded from {refinementRulesData}
- Integration claims extracted from architecture document using prose co-mention analysis
- All possible library pairs generated from skill inventory
- Skill API surfaces loaded for cross-reference
- Each gap includes evidence citations from actual skill content
- Gap analysis results displayed with count and details
- Gap findings stored as workflow state for Step 05
- Auto-proceeded to step 03

### ❌ SYSTEM FAILURE:

- Inventing APIs not present in the actual skills
- Flagging contradictions or issues (that is Step 03)
- Suggesting capability improvements (that is Step 04)
- Gaps without evidence citations from generated skills
- Parsing Mermaid diagrams instead of using prose-based co-mention analysis
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
