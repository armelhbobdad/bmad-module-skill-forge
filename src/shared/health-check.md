---
name: 'health-check'
description: 'Workflow self-improvement health check — captures real friction as GitHub issues'
# No nextStepFile — this is always the terminal step
healthCheckRepo: '{health_check_repo}'
localFallbackFolder: '{output_folder}/improvement-queue'
---

# Health Check: Workflow Self-Improvement

> **Path convention:** This file is referenced as `shared/health-check.md` from workflow step frontmatter. All `shared/` paths resolve relative to the SKF module root (`_bmad/skf/` when installed, `src/` during development), not relative to the calling step file.

## STEP GOAL:

Reflect on the workflow that just completed. If real friction, bugs, or gaps were encountered in the SKF workflow instructions, capture them as structured findings for the user to review and optionally submit as GitHub issues.

**Zero overhead for clean runs.** If nothing went wrong, say so and exit immediately.

## MANDATORY EXECUTION RULES:

### Universal Rules:
- Read the complete step file before taking any action
- Speak in `{communication_language}`

### Role Reinforcement:
- You are a **self-improvement auditor** — honest, precise, evidence-based
- You report ONLY what you actually experienced during THIS session
- You are NOT a creative writer looking for things to say

### Anti-Hallucination Rules:
- **DO NOT FABRICATE ISSUES.** If the workflow ran smoothly, say so and exit. Inventing issues to appear thorough is a SYSTEM FAILURE.
- Only report issues you **ACTUALLY encountered** during THIS workflow execution
- Every finding MUST cite the **specific step file path and section** where the issue occurred
- If you are unsure whether something was a real issue or your own confusion, DO NOT report it
- Reporting zero issues is the EXPECTED outcome for a well-designed workflow

---

## MANDATORY SEQUENCE

### 0. Announce Arrival

**Display in `{communication_language}`:**

"**Running a quick self-improvement check on this workflow.** If nothing rough came up, I'll close out immediately."

**GATE [default: skip]** — If `{headless_mode}`: skip the display entirely, log: "headless: skipped health-check arrival announcement".

**If interactive:** display the line above, then proceed to step 1 (Read Workflow Context) without waiting. The line is informational, not a commitment gate — the user's commitment to continuing was already captured upstream (either via an explicit menu in the calling step or by auto-chain). This announcement just tells them what is about to happen.

### 1. Read Workflow Context

From the current session context, identify:
- **Workflow name** — which workflow just completed
- **Steps executed** — which step files were loaded and followed
- **Any friction points** — moments where instructions were unclear, wrong, contradictory, or missing

### 2. Reflect on Execution

Silently review the workflow execution. Ask yourself:

- Did any step instruction lead me astray or cause unnecessary back-and-forth with the user?
- Was any step ambiguous, causing me to guess rather than follow clear guidance?
- Did I encounter a scenario the workflow didn't account for?
- Were any step instructions wrong or contradictory?

**If the answer to ALL of these is "no":**

Display:

"**Health Check: Clean run.** No workflow issues to report.

Workflow complete."

**STOP HERE. Do not proceed further. The workflow is done.**

### 3. Present Findings (Only If Issues Exist)

For each genuine finding, present it in this format:

"**Workflow Health Check — {N} finding(s)**

---

**Finding {i}:**

| Field | Value |
|-------|-------|
| **Severity** | `bug` / `friction` / `gap` |
| **Workflow** | {workflow name} |
| **Step File** | `src/skf-{workflow}/steps-c/{step-file-path}` |
| **Section** | {the specific section or instruction number} |

**What happened:**
{Description of the actual issue encountered during execution}

**Evidence:**
{What specifically went wrong — error, confusion, user friction, missing guidance}

**Suggested improvement:**
{Concrete, actionable change to the step file or data}

---"

**Severity definitions:**
- **`bug`** — Step instructions were wrong or contradictory
- **`friction`** — Step worked but was unclear, ambiguous, or caused unnecessary back-and-forth
- **`gap`** — A scenario arose that the workflow didn't account for at all

### 4. User Review Gate

After presenting all findings, ask:

"**Submit these findings?**

- **[Y]** Yes — submit all findings
- **[N]** No — discard all findings
- **[E]** Edit — let me revise before submitting

_You are the final filter. Reject any finding that doesn't reflect a real issue you observed._"

**HALT and wait for user input.**

#### Menu Handling:

- **IF Y:** Proceed to step 5
- **IF N:** Display "Findings discarded. Workflow complete." — STOP
- **IF E:** Let user specify which findings to keep, modify, or remove. Then re-present the revised list and ask again.

### 5. Submit Findings

**Check GitHub CLI availability:**

Run `gh auth status` to determine if the `gh` CLI is authenticated.

#### IF `gh` is available:

For each confirmed finding, create a GitHub issue:

**Command:**
```
gh issue create \
  --repo {healthCheckRepo} \
  --title "[health-check] [{severity}] {workflow}: {short description}" \
  --label "health-check,workflow-improvement,{severity}" \
  --body "{formatted body using issue template structure}"
```

**Writing rules — non-negotiable:**

- **One issue per finding.** If you observed two independent problems, submit two issues.
- **Respect the length budgets.** Finding, Expected, Actual, Impact are each ONE sentence. Evidence is 2-5 bullets, not prose. Suggested Fix is 1-3 sentences with ONE recommendation — multiple options go in the `Alternatives considered` collapsible or (better) not at all.
- **Quote, don't paraphrase.** In Evidence, cite the exact `file:line` and put the quoted text in quotes. Link the convention to the instruction that caused it.
- **Never narrate the session.** The reader wants the defect, not the story. If a sentence starts with "During my run..." or "I was trying to...", delete it.
- **If unsure whether it's a real issue, do not submit it.** Reporting zero findings is a healthy outcome.

**Issue body format:**
```markdown
## Workflow
{workflow name, e.g. `skf-create-skill`}

## Step File
`src/skf-{workflow}/steps-c/step-NN-name.md`

## Severity
`{bug | friction | gap}`
<!-- bug: instructions were wrong or contradictory -->
<!-- friction: instructions worked but caused back-and-forth or guessing -->
<!-- gap: a scenario arose that wasn't covered at all -->

## Finding
<!-- ONE sentence. What is the problem? Do not explain why yet. -->
{e.g. Step-05 forbids writes to `skills/` but does not name a staging directory.}

## Expected
<!-- ONE sentence. What did the step instruct or imply should happen? -->
{e.g. The step should name the staging directory between assembly and final write.}

## Actual
<!-- ONE sentence. What did you observe instead? -->
{e.g. No staging path specified, so artifacts were written to `skills/{name}/` and step-07 had to reorganize them.}

## Evidence
<!-- Bulleted `file:line` citations. 2-5 bullets. No narrative prose. -->
- `path/to/file.md:17` — "quoted text from the file"
- `path/to/other.md:62` — brief note on what it shows

## Impact
<!-- ONE sentence. What did this cost in THIS session? -->
{e.g. 50KB of artifacts written to the wrong path; step-07 required a file-move pass.}

## Suggested Fix
<!-- ONE recommended change. 1-3 sentences. Do NOT list multiple options here. -->
{e.g. Add a rule to step-05 naming `_bmad-output/{skill-name}/` as the staging directory used by step-06 validation.}

<details>
<summary>Alternatives considered (optional)</summary>

<!-- Only fill this if you seriously considered 2+ approaches. Keep under 100 words total. -->

</details>

## Environment
| Field | Value |
|-------|-------|
| Date | {ISO date} |
| OS | {e.g. macOS 15.2, Ubuntu 24.04, Windows 11} |
| AI Editor | {e.g. Claude Code, Cursor, Windsurf} |
| Model | {e.g. Claude Opus 4.6, Claude Sonnet 4.6} |
| Forge Tier | {Quick/Forge/Forge+/Deep, else N/A} |
| SKF Version | {from `{project-root}/_bmad/skf/VERSION`, else N/A} |
```

After creating all issues, display:

"**{N} issue(s) created on {healthCheckRepo}:**
{list each issue URL}

Workflow complete."

#### IF `gh` is NOT available:

For each confirmed finding, write a local file to `{localFallbackFolder}/`:

**Filename:** `hc-{workflow}-{timestamp}.md` (one file per finding, timestamp as YYYYMMDD-HHmmss)

**File content:** Same structured format as the issue body above, with YAML frontmatter:

```yaml
---
type: workflow-health-finding
workflow: {workflow name}
step_file: {step file path}
severity: {bug | friction | gap}
date: {ISO date}
---
```

After writing all files, display:

"**{N} finding(s) saved locally:**
{list each file path}

GitHub CLI is not available. To submit these as issues, run:
`gh issue create --repo {healthCheckRepo} --title \"[title]\" --body-file {file-path}`

Or open them manually at: <https://github.com/{healthCheckRepo}/issues/new/choose>

Workflow complete."

---

## CRITICAL STEP COMPLETION NOTE

This is the TERMINAL step — shared across all SKF workflows. After the health check completes (clean run or findings submitted/discarded), the workflow is fully done. No further steps to load.

---

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:

- Clean runs exit immediately with no findings (most common outcome)
- Findings cite specific step files and sections with real evidence
- User review gate presented before any submission
- GitHub issues created with correct labels and structured body (when `gh` available)
- Local fallback files written with clear manual submission instructions (when `gh` unavailable)
- Workflow ends cleanly

### SYSTEM FAILURE:

- Fabricating issues that were not actually encountered during the session
- Reporting vague issues without step file citations ("the workflow was confusing")
- Skipping the user review gate
- Creating issues without user confirmation
- Not providing the local fallback when `gh` is unavailable
- Continuing to load steps after this one (this is terminal)

**Master Rule:** Honesty is the only policy. Zero findings is the expected, healthy outcome. Fabricating issues to appear thorough undermines the entire self-improvement system and constitutes SYSTEM FAILURE.
