---
name: 'step-03-issue-detection'
description: 'Find contradictions between architecture claims and verified API reality from skills and optional VS report'

nextStepFile: './step-04-improvements.md'
refinementRulesData: '../data/refinement-rules.md'
---

# Step 3: Issue Detection

## STEP GOAL:

Find contradictions between what the architecture document claims and what the generated skills reveal about actual API surfaces. Detect language boundary issues not addressed, protocol mismatches assumed away, and missing bridge layers. If a VS feasibility report is available, incorporate RISKY and BLOCKED verdicts as confirmed issues.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are an architecture refinement analyst performing contradiction detection
- ✅ Every issue must cite evidence from actual skill content AND the architecture claim it contradicts
- ✅ Apply the issue detection rules from {refinementRulesData} strictly

### Step-Specific Rules:

- 🎯 Focus ONLY on contradictions between architecture claims and skill API reality
- 🚫 FORBIDDEN to detect undocumented integration paths — that was Step 02
- 🚫 FORBIDDEN to suggest capability expansions — that is Step 04
- 💬 Every issue MUST cite both the architecture claim AND the contradicting skill evidence

## EXECUTION PROTOCOLS:

- Load refinement rules for issue detection criteria
- Extract all integration claims from the architecture document
- Verify each claim against skill API surfaces
- Incorporate VS report verdicts if available
- Append issue findings as workflow state for Step 05
- Only issue detection — no gap analysis, no improvement suggestions

## CONTEXT BOUNDARIES:

- Available: Architecture document content, skill inventory and SKILL.md files, VS feasibility report (if provided), refinement rules
- Focus: Finding contradictions between documented claims and verified API reality
- Limits: Only detect issues — do not fill gaps or suggest improvements
- Dependencies: Step 01 (skill inventory, architecture doc, VS report status), Step 02 (gap analysis complete)

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise.

### 1. Reference Refinement Rules

Use the refinement rules loaded in Step 01 from `{refinementRulesData}`. If not available in context, reload from `{refinementRulesData}`.

Extract: issue classification (API Mismatch, Protocol Contradiction, Language Boundary Ignored, Type Incompatibility), VS report integration rules, and citation format.

### 2. Extract Integration Claims from Architecture

Parse the architecture document for specific claims about how technologies interact.

**Claim types to extract:**
- **API claims:** "Library X provides/exposes/exports {function/endpoint}"
- **Protocol claims:** "Library X communicates via {protocol}"
- **Data flow claims:** "Data flows from X to Y as {format}"
- **Integration claims:** "X and Y integrate through {mechanism}"
- **Capability claims:** "Library X handles {capability}"

For each claim, record:
- The exact text or paraphrase from the architecture
- The section where it appears
- The libraries referenced

### 3. Verify Claims Against Skill API Surfaces

For each extracted claim, load the relevant skill(s) and check:

**API Mismatch check:**
- Does the claimed API actually exist in the skill's export list?
- Does the function signature match what the architecture describes?
- If the architecture describes an API that does not appear in the skill: flag as issue

**Protocol Contradiction check:**
- Does the skill document the protocol the architecture assumes?
- If the architecture claims gRPC but the skill shows HTTP-only: flag as issue

**Language Boundary check:**
- If two libraries are in different languages, does the architecture describe a bridge mechanism?
- If the architecture assumes direct calls across language boundaries without FFI/IPC: flag as issue

**Type Incompatibility check:**
- Does the architecture assume type compatibility that the skills contradict?
- If Library A exports Type X but the architecture claims Library B consumes it, and Library B expects Type Y: flag as issue

### 4. Incorporate VS Report (If Available)

If `vs_report_available` is true:

**Load the VS feasibility report and extract verdicts:**
- **Risky verdicts** (match case-insensitively: "Risky", "RISKY", "risky"): Promote to confirmed issues with the VS evidence as additional citation
- **Blocked verdicts** (match case-insensitively: "Blocked", "BLOCKED", "blocked"): Promote to critical issues requiring architecture redesign
- **Plausible verdicts:** Note informatively — Plausible is not an issue by itself. Only flag as a potential issue if the VS rationale text explicitly states "no direct API evidence" or "weak evidence"

**For each VS-sourced issue, include dual citations:**
- Evidence from the skill content
- Verdict and rationale from the VS report

If `vs_report_available` is false: Skip this section. Issue detection proceeds with skill data only.

### 5. Document Each Issue

For each detected issue, apply the citation format from {refinementRulesData}:

```
**[ISSUE]**: {description}

Architecture states: "{quoted claim from original document}" (Section: {section_name})
Skill reality: {skill_name} exports: `{actual_api}` — {explanation of contradiction}
{IF VS report}: VS verdict: {Risky|Blocked} for {pair} — {VS rationale}

Suggestion: {specific correction with API evidence}
```

**Severity classification:**
- **Critical:** Blocked VS verdicts, fundamental language barriers with no bridge
- **Major:** Risky VS verdicts, protocol mismatches, missing bridge layers
- **Minor:** Plausible VS verdicts where the VS rationale explicitly states "no direct API evidence" or "weak evidence", minor type differences with easy conversion

### 6. Display Issue Detection Results

"**Pass 2: Issue Detection — Architecture vs. API Reality**

**Issues Found:** {count} ({critical_count} critical, {major_count} major, {minor_count} minor)

{IF issues found:}
| # | Libraries | Issue Type | Severity | Summary |
|---|-----------|-----------|----------|---------|
| {n} | {libs} | {issue_type} | {severity} | {brief description} |

{For each issue, display the full citation with evidence and suggestion}

{IF no issues found:}
**No contradictions detected.** Architecture claims align with verified skill API surfaces.

**Proceeding to improvement detection...**"

Store all issue findings as workflow state for Step 05. To ensure durability across long runs, also append a `<!-- [RA-ISSUES] ... -->` comment block to `{forge_data_folder}/ra-state-{project_name}.md` containing the **complete formatted issue findings** (full citation blocks with architecture claims, skill evidence, VS verdicts, severity, and suggestions — not just counts) — Step 05 can read this back if context degrades. **Do NOT write to `{output_folder}/refined-architecture-{project_name}.md` — that file is created only in step-05.**

### 7. Auto-Proceed to Next Step

Load, read the full file and then execute `{nextStepFile}`.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Refinement rules loaded from {refinementRulesData}
- All integration claims extracted from architecture document
- Each claim verified against actual skill API surfaces
- VS report verdicts incorporated if report was provided
- Every issue includes both architecture citation AND contradicting skill evidence
- Issues classified by severity (Critical, Major, Minor)
- Issue detection results displayed with count and details
- Issue findings stored as workflow state for Step 05
- Auto-proceeded to step 04

### ❌ SYSTEM FAILURE:

- Issues without evidence from actual skills (speculation)
- Not citing the architecture claim that is contradicted
- Filling gaps (that was Step 02) or suggesting improvements (that is Step 04)
- Ignoring VS report verdicts when the report was provided
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
