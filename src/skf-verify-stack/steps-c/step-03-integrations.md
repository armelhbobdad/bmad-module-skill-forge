---
nextStepFile: './step-04-requirements.md'
integrationRulesData: 'references/integration-verification-rules.md'
outputFile: '{forge_data_folder}/feasibility-report-{project_name}.md'
---

# Step 3: Integration Verification

## STEP GOAL:

Cross-reference API surfaces between library pairs that the architecture document claims work together. For each integration pair, verify language compatibility, protocol alignment, type compatibility, and documentation cross-references. Produce an evidence-backed verdict for each integration.

## Rules

- Focus only on integration pair verification using skill API surfaces
- Do not evaluate requirements coverage (Step 04) or parse Mermaid diagrams
- Every verdict must include evidence citations from the skills

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

<!-- Subagent delegation: read SKILL.md files in parallel, return compact JSON -->

For each library in an integration pair, delegate SKILL.md reading to a parallel subagent. Launch up to **8 subagents concurrently** (batch if needed). Each subagent receives one skill's SKILL.md path and MUST:
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
- `exports` — export names array (populated for individual skills; empty for stack skills)
- `stats.exports_documented` — export count
- `confidence_tier` — extraction confidence level

Store collected API surface summaries for cross-referencing.

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

