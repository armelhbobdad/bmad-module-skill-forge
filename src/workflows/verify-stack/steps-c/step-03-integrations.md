---
name: 'step-03-integrations'
description: 'Pass 2 — cross-reference API surfaces between library pairs based on integration claims in the architecture document'

nextStepFile: './step-04-requirements.md'
integrationRulesData: '../data/integration-verification-rules.md'
outputFile: '{forge_data_folder}/feasibility-report-{project_name}.md'
---

# Step 3: Integration Verification

## STEP GOAL:

Cross-reference API surfaces between library pairs that the architecture document claims work together. For each integration pair, verify language compatibility, protocol alignment, type compatibility, and documentation cross-references. Produce an evidence-backed verdict for each integration.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a stack verification analyst performing integration feasibility analysis
- ✅ Every verdict must cite evidence from the actual skill content — no speculation
- ✅ Apply the verification protocol strictly — do not skip compatibility checks

### Step-Specific Rules:

- 🎯 Focus ONLY on integration pair verification using skill API surfaces
- 🚫 FORBIDDEN to evaluate requirements coverage — that is Step 04
- 🚫 FORBIDDEN to parse Mermaid diagrams — use prose-based co-mention analysis only
- 💬 Every verdict MUST include evidence citations from the skills

## EXECUTION PROTOCOLS:

- 🎯 Extract integration claims from architecture document prose
- 💾 Load skill API surfaces and cross-reference each integration pair
- 📖 Append Integration Verdicts section to {outputFile}
- 🚫 Only integration analysis — no requirements checking, no synthesis

## CONTEXT BOUNDARIES:

- Available: Architecture document content, skill SKILL.md and metadata.json files, integration verification rules
- Focus: Pairwise integration compatibility between skills
- Limits: Only verify pairs explicitly claimed in the architecture document — do not invent integration relationships
- Dependencies: Step 01 (skill inventory), Step 02 (coverage matrix — only verify skills that exist)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Load Integration Verification Rules

Load `{integrationRulesData}` for the cross-reference verification protocol.

Extract: verification checks (language boundary, protocol compatibility, type compatibility, documentation cross-reference), verdict criteria, and evidence requirements.

### 2. Extract Integration Claims

Parse the architecture document for statements describing two or more technologies working together.

**Detection method — prose-based co-mention analysis:**
- Identify sentences or paragraphs where two or more technology names appear together
- Look for integration verbs: "connects to", "communicates with", "wraps", "extends", "consumes", "produces", "bridges", "integrates with", "sits between"
- Look for data flow descriptions: "{A} sends data to {B}", "{A} results are consumed by {B}"
- Look for layer boundary descriptions: "{A} at the API layer connects to {B} at the data layer"

**CRITICAL:** Do NOT parse Mermaid diagram syntax. Use only prose text for co-mention detection.

**Build integration pairs list:**
- Each pair: `{library_a, library_b, architectural_context}`
- `architectural_context`: the quoted text or paraphrased description of their relationship

**Filter:** Only include pairs where BOTH libraries have a corresponding skill (Covered in Step 02). Skip pairs involving Missing skills — they cannot be verified.

### 3. Load Skill API Surfaces

For each library in an integration pair, load the skill artifacts:

**From SKILL.md, extract:**
- Exported functions and their signatures
- Exported types, interfaces, and classes
- Protocol indicators (HTTP, gRPC, WebSocket, message queue, file I/O, IPC)
- Data format indicators (JSON, protobuf, CSV, binary, streaming)

**From metadata.json, extract:**
- `language` — primary programming language
- `exports` — export names array (populated for individual skills; empty for stack skills)
- `stats.exports_documented` — export count
- `confidence_tier` — extraction confidence level

Store loaded API surfaces for cross-referencing.

### 4. Cross-Reference Each Integration Pair

For each integration pair `{library_a, library_b}`, apply the verification protocol from `{integrationRulesData}`:

**Check 1 — Language Boundary:**
- Same language → compatible
- Different languages → check for FFI, IPC, or network protocol bridge
- If no bridge mechanism documented → flag as risk

**Check 2 — Protocol Compatibility:**
- Both use same protocol (e.g., both HTTP) → compatible
- Complementary protocols (e.g., HTTP client + HTTP server) → compatible
- Incompatible protocols with no adapter → flag as risk

**Check 3 — Type Compatibility:**
- Shared types or compatible serialization formats → compatible
- Incompatible type systems with no conversion layer → flag as risk

**Check 4 — Documentation Cross-Reference:**
- Skill A mentions skill B's library (or vice versa) → strong evidence
- Neither skill mentions the other → weak evidence (plausible but unverified)

**Assign verdict per pair:**
- **Verified** — all checks pass with evidence from both skills
- **Plausible** — checks pass but evidence is indirect or incomplete
- **Risky** — one or more checks flag compatibility concerns
- **Blocked** — fundamental incompatibility detected (language barrier with no bridge, incompatible protocols)

**Each verdict MUST include:**
- Which checks passed and which flagged
- Evidence citations: specific exports, types, or protocol references from the skills

### 5. Display Integration Results

"**Pass 2: Integration Verification**

| Library A | Library B | Context | Verdict | Evidence |
|-----------|-----------|---------|---------|----------|
| {lib_a} | {lib_b} | {brief context} | {Verified/Plausible/Risky/Blocked} | {key evidence} |

**Summary:** {verified_count} Verified, {plausible_count} Plausible, {risky_count} Risky, {blocked_count} Blocked

{IF zero integration pairs found:}
**No integration claims detected in the architecture document prose.** Ensure your architecture document describes relationships between technologies in text form (not exclusively in Mermaid diagrams). Coverage-only analysis was performed.

{IF any Risky:}
**Risky Integrations — Recommendations:**
{For each risky pair:}
- `{lib_a}` ↔ `{lib_b}`: {specific concern}. **Recommendation:** {prescriptive action}

{IF any Blocked:}
**Blocked Integrations — Action Required:**
{For each blocked pair:}
- `{lib_a}` ↔ `{lib_b}`: {fundamental incompatibility}. **Recommendation:** {prescriptive action}"

### 6. Append to Report

Write the **Integration Verdicts** section to `{outputFile}`:
- Include the full integration verdicts table with evidence
- Include recommendations for Risky and Blocked pairs
- Update frontmatter: append `'step-03-integrations'` to `stepsCompleted`
- Set `integrations_verified`, `integrations_plausible`, `integrations_risky`, `integrations_blocked` counts

### 7. Auto-Proceed to Next Step

**Early halt guard:** If ALL integration pairs are Blocked, present: "**All integrations are Blocked** — fundamental incompatibilities detected across all library pairs. Remaining analysis will produce limited value. **[X] Halt workflow (recommended)** | **[C] Continue anyway**" — wait for user input. If X: halt with: "**Workflow halted — all integrations blocked.** Integration Verdicts saved to `{outputFile}`. Run **[VS]** after applying architectural changes. **Blocked integrations:** {list each blocked pair with reason}." If C: continue.

{IF NOT halted (user selected C, or early halt guard did not trigger):}

"**Proceeding to requirements verification...**"

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Integration rules loaded from {integrationRulesData}
- Integration claims extracted from architecture document prose (not Mermaid diagrams)
- Skill API surfaces loaded for each library in integration pairs
- All four verification checks applied to each pair
- Every verdict includes evidence citations from actual skill content
- Recommendations provided for every Risky and Blocked integration
- Integration Verdicts section appended to {outputFile}
- Auto-proceeded to step 04

### ❌ SYSTEM FAILURE:

- Parsing Mermaid diagrams instead of using prose-based co-mention analysis
- Verdicts without evidence citations from actual skills
- Inventing integration relationships not described in the architecture document
- Skipping any of the four verification checks
- Evaluating requirements coverage (that is Step 04)
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
