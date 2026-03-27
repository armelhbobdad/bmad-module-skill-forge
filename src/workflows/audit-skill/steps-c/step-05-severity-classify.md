---
name: 'step-05-severity-classify'
description: 'Grade every drift finding by severity using classification rules'

nextStepFile: './step-06-report.md'
outputFile: '{forge_data_folder}/{skill_name}/drift-report-{timestamp}.md'
severityRulesFile: '../data/severity-rules.md'
---

# Step 5: Severity Classification

## STEP GOAL:

Grade every drift finding from Steps 03 and 04 by severity level (CRITICAL/HIGH/MEDIUM/LOW) using the classification rules. Calculate the overall drift score and produce a categorized findings table with confidence tier labels.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER generate content without user input
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- ⚙️ TOOL/SUBPROCESS FALLBACK: If any instruction references a subprocess, subagent, or tool you do not have access to, you MUST still achieve the outcome in your main context thread
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

### Role Reinforcement:

- ✅ You are a skill auditor performing severity assessment
- ✅ Classification must be deterministic — same finding always gets same severity
- ✅ Apply rules strictly — do not invent new severity categories or soften classifications

### Step-Specific Rules:

- 🎯 Focus only on classifying severity of existing findings
- 🚫 FORBIDDEN to discover new drift items — only classify what Steps 03-04 found
- 🚫 FORBIDDEN to suggest remediation — that happens in Step 06
- 💬 Use subprocess Pattern 3 (data operations — main thread Read + process in Claude Code, script in CLI) to load severity rules and classify. See [knowledge/tool-resolution.md](../../../knowledge/tool-resolution.md)
- ⚙️ If subprocess unavailable, load rules and classify in main thread

## EXECUTION PROTOCOLS:

- 🎯 Load {severityRulesFile} and apply to every finding
- 💾 Append ## Severity Classification section to {outputFile}
- 📖 Update {outputFile} frontmatter stepsCompleted when complete
- 🚫 Only classification — no new findings, no remediation

## CONTEXT BOUNDARIES:

- Available: Structural drift findings (Step 03), semantic drift findings (Step 04 if Deep), severity rules
- Focus: Applying deterministic severity classification to every finding
- Limits: Do not discover new drift, do not suggest fixes
- Dependencies: Steps 03 (and optionally 04) must be complete

## MANDATORY SEQUENCE

**CRITICAL:** Follow this sequence exactly. Do not skip, reorder, or improvise unless user explicitly requests a change.

### 1. Load Severity Rules

Launch a subprocess (Pattern 3 — data operations) that:
1. Loads {severityRulesFile}
2. Extracts classification criteria for each severity level
3. Returns structured rules to parent

**If subprocess unavailable:** Load {severityRulesFile} directly in main thread.

**Rules summary:**
- **CRITICAL:** Removed/renamed exports, changed signatures (breaking changes)
- **HIGH:** New public API not in skill (>3), removed helpers used in patterns, deprecated APIs
- **MEDIUM:** Implementation changes behind stable API, 1-3 new exports, moved functions
- **LOW:** Style/convention changes, comments, whitespace, internal functions

### 2. Collect All Findings

Gather all drift items from the report:

**From ## Structural Drift (Step 03):**
- Added exports
- Removed exports
- Changed exports

**From ## Semantic Drift (Step 04, if Deep tier):**
- New patterns
- Changed conventions
- Dependency shifts
- Deprecated patterns

Count total findings to classify.

### 3. Apply Severity Classification

For EACH finding, apply the severity rules:

**Structural findings classification:**
- Removed export → CRITICAL (breaking: skill references something that no longer exists)
- Changed signature → CRITICAL (breaking: skill documents wrong parameters/return type)
- Renamed export → CRITICAL (breaking: skill references old name)
- Moved export (same signature) → MEDIUM (non-breaking but location in skill is wrong)
- Added export (>3 total) → HIGH (significant API surface not documented)
- Added export (1-3 total) → MEDIUM (minor gap in coverage)

**Semantic findings classification:**
- Deprecated pattern still in skill → HIGH (skill teaches outdated approach)
- Changed convention → MEDIUM (skill may use old style)
- New pattern detected → MEDIUM (skill doesn't cover new approach)
- Dependency shift → MEDIUM (skill may reference wrong dependencies)

Record for each finding: original finding + assigned severity level.

### 4. Calculate Overall Drift Score

Apply scoring rules from {severityRulesFile}:

| Score | Criteria |
|-------|----------|
| **CLEAN** | 0 findings at any level |
| **MINOR** | LOW findings only, no MEDIUM+ |
| **SIGNIFICANT** | Any MEDIUM or HIGH findings, no CRITICAL |
| **CRITICAL** | Any CRITICAL findings present |

### 5. Compile Severity Classification Section

Append to {outputFile}:

```markdown
## Severity Classification

**Overall Drift Score: {CLEAN / MINOR / SIGNIFICANT / CRITICAL}**

### CRITICAL ({count})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### HIGH ({count})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### MEDIUM ({count})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### LOW ({count})

| # | Finding | Type | Detail | Location | Confidence |
|---|---------|------|--------|----------|------------|
| 1 | {finding} | {structural/semantic} | {detail} | {file}:{line} | {T1/T2} |

### Classification Summary

| Severity | Count | Source |
|----------|-------|--------|
| CRITICAL | {count} | {structural: N, semantic: N} |
| HIGH | {count} | {structural: N, semantic: N} |
| MEDIUM | {count} | {structural: N, semantic: N} |
| LOW | {count} | {structural: N, semantic: N} |
| **Total** | {total} | |
```

### 6. Update Report and Auto-Proceed

Update {outputFile} frontmatter:
- Append `'step-05-severity-classify'` to `stepsCompleted`
- Set `drift_score` to calculated overall score

### 7. Present MENU OPTIONS

Display: "**Severity classification complete. Overall drift score: {score}. Proceeding to report generation...**"

#### Menu Handling Logic:

- After severity classification section is appended and frontmatter updated, immediately load, read entire file, then execute {nextStepFile}

#### EXECUTION RULES:

- This is an auto-proceed analysis step with no user choices
- Proceed directly to next step after completion

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the ## Severity Classification section has been appended to {outputFile} with all findings classified will you then load and read fully `{nextStepFile}` to execute and begin final report generation.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Severity rules loaded from {severityRulesFile}
- Every finding from Steps 03-04 classified (none missed)
- Classification is deterministic — follows rules strictly
- Overall drift score calculated correctly
- Structured tables with severity, source type, and confidence
- Frontmatter drift_score and stepsCompleted updated

### ❌ SYSTEM FAILURE:

- Inventing new severity categories beyond CRITICAL/HIGH/MEDIUM/LOW
- Missing any finding from classification (incomplete coverage)
- Softening classifications that should be CRITICAL
- Discovering new drift items (classification only, not discovery)
- Suggesting remediation (that is Step 06)
- Hardcoded paths instead of frontmatter variables

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
