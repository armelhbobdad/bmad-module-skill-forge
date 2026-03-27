---
name: 'step-04-improvements'
description: 'Suggest capability expansions from skill data not leveraged in the architecture'

nextStepFile: './step-05-compile.md'
refinementRulesData: '../data/refinement-rules.md'
---

# Step 4: Improvement Detection

## STEP GOAL:

Identify capability expansions — library features documented in the generated skills that the architecture does not leverage. Detect unused capabilities, cross-library synergies visible from skill API surfaces, and alternative patterns that could strengthen the architecture. For each improvement, document the capability and suggest how to incorporate it.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are an architecture refinement analyst identifying untapped capabilities
- ✅ Every improvement must cite specific APIs from the generated skills — no speculation
- ✅ Improvements are suggestions, not mandates — present them as optional enhancements

### Step-Specific Rules:

- 🎯 Focus ONLY on capability expansions not leveraged in the architecture
- 🚫 FORBIDDEN to detect gaps (Step 02) or issues (Step 03) — those are already captured
- 🎯 Improvements are ADDITIVE suggestions — they enhance, not contradict, the architecture
- 💬 Every improvement MUST include evidence citations from actual skill content

## EXECUTION PROTOCOLS:

- Load refinement rules for improvement detection criteria
- Compare full skill API surfaces against architecture usage
- Detect unused capabilities, cross-library synergies, and alternative patterns
- Append improvement findings as workflow state for Step 05
- Only improvement detection — no gap or issue analysis

## CONTEXT BOUNDARIES:

- Available: Architecture document content, skill inventory and SKILL.md files, refinement rules
- Focus: Finding capabilities in skills that the architecture does not use
- Limits: Only detect improvements — do not re-detect gaps or issues from earlier steps
- Dependencies: Step 01 (skill inventory), Steps 02-03 (complete — do not duplicate findings)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Reference Refinement Rules

Use the refinement rules loaded in Step 01 from `{refinementRulesData}`. If not available in context, reload from `{refinementRulesData}`.

Extract: improvement classification (Unused Capability, Cross-Library Synergy, Alternative Pattern), detection method, and citation format.

### 2. Build Architecture Usage Map

For each library referenced in the architecture document, extract how it is used:

- What capabilities are described (e.g., "Loro for real-time data sync")
- What APIs or features are referenced
- What role it plays in the architecture

This creates a map of `{library} -> {described_usage[]}` for comparison against full skill API surfaces.

### 3. Compare Skill API Surfaces Against Architecture Usage

For each skill in the inventory:

**Load the full API surface from SKILL.md:**
- All exported functions with signatures
- All exported types and interfaces
- All documented capabilities and features
- All protocol support indicators

**Compare against the architecture usage map:**
- Which exports does the architecture reference or imply usage of?
- Which exports are NOT referenced in the architecture at all?

**For each unreferenced capability:**
- Evaluate relevance: would this capability strengthen the architecture?
- Skip trivial or internal-only exports (utilities, helpers, debug functions)
- Flag capabilities that could address architectural concerns or expand functionality

### 4. Detect Cross-Library Synergies

Examine pairs of skills for complementary capabilities not exploited in the architecture:

- Does Library A export an event system that Library B could consume?
- Does Library A produce a data format that Library B has an optimized processor for?
- Do two libraries offer overlapping capabilities that could be unified?

**Only flag synergies where both sides have documented APIs** — do not speculate about undocumented features.

### 5. Document Each Improvement

For each detected improvement, apply the citation format from {refinementRulesData}:

```
**[IMPROVEMENT]**: {description}

Evidence:
- {skill_name} exports: `{function}({params}) -> {return_type}`
- Architecture uses: {what the architecture currently describes}
- Untapped: {what the skill offers that the architecture does not mention}

Suggestion: {how to incorporate this capability into the architecture}
```

**Categorize improvements:**
- **High:** Capabilities that address known architectural concerns or significantly expand functionality
- **Medium:** Capabilities that add convenience or efficiency improvements
- **Low:** Capabilities that are nice-to-have but not impactful

### 6. Display Improvement Suggestions

"**Pass 3: Improvement Detection — Untapped Capabilities**

**Improvements Found:** {count} ({high_count} high value, {medium_count} medium, {low_count} low)

{IF improvements found:}
| # | Library | Improvement Type | Value | Summary |
|---|---------|-----------------|-------|---------|
| {n} | {lib} | {type} | {value} | {brief description} |

{For each improvement, display the full citation with evidence and suggestion}

{IF no improvements found:}
**No untapped capabilities detected.** The architecture fully leverages the skill API surfaces.

**Proceeding to compile refined architecture...**"

Store all improvement findings as workflow state for Step 05. To ensure durability across long runs, also append a `<!-- [RA-IMPROVEMENTS] ... -->` comment block to `{forge_data_folder}/ra-state-{project_name}.md` containing the **complete formatted improvement findings** (full citation blocks with evidence, value ratings, and suggestions — not just counts) — Step 05 can read this back if context degrades. **Do NOT write to `{output_folder}/refined-architecture-{project_name}.md` — that file is created only in step-05.**

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Refinement rules loaded from {refinementRulesData}
- Architecture usage map built for each referenced library
- Full skill API surfaces compared against architecture usage
- Cross-library synergies checked for complementary capabilities
- Every improvement includes evidence citations from actual skill content
- Improvements categorized by value (High, Medium, Low)
- Improvement results displayed with count and details
- Improvement findings stored as workflow state for Step 05
- Auto-proceeded to step 05

### ❌ SYSTEM FAILURE:

- Improvements without evidence from actual skills (speculation)
- Re-detecting gaps (Step 02) or issues (Step 03)
- Presenting trivial internal-only exports as improvements
- Not categorizing improvements by value
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
