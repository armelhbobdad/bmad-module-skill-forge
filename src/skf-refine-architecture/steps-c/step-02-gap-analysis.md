---
nextStepFile: './step-03-issue-detection.md'
refinementRulesData: 'references/refinement-rules.md'
---

# Step 2: Gap Analysis

## STEP GOAL:

Find undocumented integration paths — library pairs that have compatible APIs (from the generated skills) but are not described in the architecture document. For each gap, document what APIs connect and propose an architecture section describing the integration.

## Rules

- Focus only on undocumented integration paths (gaps) — do not detect contradictions (Step 03) or suggest expansions (Step 04)
- Every gap must include evidence citations from actual skill content

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

<!-- Subagent delegation: read SKILL.md files in parallel, return compact JSON -->

For each library in the skill inventory, delegate reading to a parallel subagent. Launch up to **8 subagents concurrently** (batch larger inventories in rounds of 8).

**Each subagent receives one skill's SKILL.md path and MUST:**
1. Read the SKILL.md file
2. Extract the API surface
3. ONLY return this compact JSON — no prose, no extra commentary:

```json
{
  "skill_name": "...",
  "exports": ["functionName(params): ReturnType", "..."],
  "protocols": ["HTTP", "gRPC", "WebSocket", "message queue", "file I/O", "IPC"],
  "data_formats": ["JSON", "protobuf", "CSV", "binary", "streaming"]
}
```

**Extraction rules for subagents:**
- `exports`: exported functions with signatures, exported types/interfaces/classes
- `protocols`: any protocol indicators found in the SKILL.md
- `data_formats`: any data format indicators found in the SKILL.md
- If a field has no matches, return an empty array `[]`

**Parent collects all subagent JSON summaries.** Do not load full SKILL.md content into parent context.

**From metadata.json (read in parent — lightweight), also extract:**
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

