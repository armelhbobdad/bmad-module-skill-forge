---
name: 'health-check'
description: 'Workflow self-improvement health check — captures real friction as GitHub issues'
# No nextStepFile — this is always the terminal step
healthCheckRepo: '{health_check_repo}'
localFallbackFolder: '{forge_data_folder}/improvement-queue'  # forge workspace artifact — use forge_data_folder (single, unambiguous SKF var), NOT output_folder (a Core Config var that resolves differently across co-installed BMad modules)
seenCachePath: '$HOME/.skf/health-check-seen.json'
liveSubmitSeverities: ['bug']  # friction/gap go local-queue-default with explicit opt-in
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
| **Step File** | `src/skf-{workflow}/references/{step-file-path}` |
| **Section** | {the specific section or instruction number — use a stable section heading slug, not line numbers} |
| **Fingerprint** | `fp-{7-hex}` — first 7 hex chars of `sha1("{severity}|{workflow}|{step_file}|{section-slug}")` |

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

### 5. Route Each Finding by Severity

Before any submission, route each confirmed finding by severity:

- **`bug`** → live-submit path (step 5a below). High signal, priority for maintainers.
- **`friction`** / **`gap`** → local-queue by default (step 5c below). These are the most subjective categories and produce the most near-duplicates. Ask the user once per session: *"Also submit the {N} friction/gap finding(s) as GitHub issues? \[y/N]"* — only if the user affirms explicitly, route them through 5a.

### 5a. Live-Submit Path: Compute Fingerprint and Dedup

For each finding routed to live-submit:

**1. Compute the fingerprint** — a deterministic 7-hex dedup key:

```
fp="fp-$(printf '%s|%s|%s|%s' "{severity}" "{workflow}" "{step_file}" "{section-slug}" | sha1sum | cut -c1-7)"
```

The `section-slug` is a kebab-case normalized section heading (e.g. `missing-staging-path`). Never include line numbers — they drift when files are edited.

**2. Check the local seen-cache** at `{seenCachePath}`:

Read `{seenCachePath}`. A missing file, an empty file, or one that does not parse as JSON is an empty cache — never an error, never a reason to halt.

**Presence in the cache is not the verdict.** A fingerprint whose defect was already fixed must NOT suppress: a fresh sighting of a fixed defect is a *regression*, and it is the single most valuable report this loop can produce. Look up the fingerprint and work these branches in order, stopping at the first that matches:

1. **No record for this fingerprint** → `unseen`. Go to sub-step 3.
2. **Record with `"action": "resolved"`** → `regression`. Recorded by hand when the defect was fixed. Go to sub-step 3 and apply the regression treatment below.
3. **Record with `"action"` of `created`, `reacted`, or `commented`, and a non-empty `issue_url`** → you must decide whether that issue is still live before you may suppress. The cache is machine-local and records only what *this* user did; the issue's own state is shared, so it is the better authority. Run exactly this, and give it a hard time bound so a hung network can never strand the run:

   ```
   timeout 10 gh issue view {issue_url} --json state,stateReason --jq '.state + "/" + (.stateReason // "")'
   ```

   - `CLOSED/COMPLETED`, or `MERGED` (the record points at a resolving PR) → `regression`. It was fixed and closed out.
   - `CLOSED/NOT_PLANNED` → `handled`. **Not** a fix: this is how the dedup Action closes a duplicate, and how a maintainer closes a wontfix. Treating it as a regression would file a REGRESSION issue against a defect nobody ever fixed, every session, forever.
   - `OPEN` → `handled`. Already filed and still being tracked.
   - Any failure at all (offline, timeout, no auth, deleted issue, unparseable output) → `handled`. This refinement never blocks a run and never halts on error.
4. **Record with one of those actions but an empty `issue_url`** → `handled`. There is no issue to consult, so the local record stands.
5. **Record with no `action`, or any other value** → `unrecognized`. Hand-edited, or written by a newer version of this file, so it cannot be confirmed handled. Go to sub-step 3 as an ordinary submission.

**`handled` is the only verdict that suppresses.** Skip submission silently and log: `"fp-{hash}: already handled on {date}, issue {url} — skipping"`. Every other verdict proceeds to sub-step 3.

**Why anything uncertain reports instead of suppressing.** A duplicate report is self-healing: the dedup Action closes it and moves the upvote to the canonical issue. A silenced regression is caught by nothing at all. When the verdict is in doubt, report.

**Regression treatment** (verdicts `regression` only). Carry the prior record forward so the recurrence can never be filed as a first sighting:

- Append ` — REGRESSION` to the issue title, after `{short description}`.
- Add a `## Regression` section immediately above `## Finding`, containing one line: `Regression of {issue_url}, resolved {date}.` If the prior record has no `issue_url`, write `Regression of a previously resolved local finding, resolved {date}.` The `{fp}` label still ties the two together server-side.
- Leave `## Finding` and the other one-sentence sections exactly as specified below. The backlink lives in its own section precisely so those budgets are untouched.

**What this does and does not catch.** The fingerprint is `sha1` over the section slug, so a fix that renames or relocates the section it touches changes the fingerprint. Such a regression arrives as `unseen` and is reported as a first sighting, which is safe but unlinked. These branches catch the regressions that recur under the same heading in the same step file, which is the case where the old behaviour was silent.

**3. Check GitHub CLI availability** with `gh auth status`. If `gh` is unavailable, fall through to step 5c (local fallback).

**4. Remote dedup search** — one deterministic call:

```
gh search issues --repo {healthCheckRepo} --state open "{fp} in:title" --json number,url,title --limit 1
```

**5a-i. If a matching open issue exists:**

Present to user:

> "**Matching report found:** #{N} — {title}
>
> Your finding has the same fingerprint `{fp}`. Options:
> - **\[R]** React (👍) on the existing issue — silent upvote, adds no comment
> - **\[C]** React + comment with YOUR environment/evidence delta (use only if it materially differs from the original)
> - **\[N]** Create a new issue anyway — only if you're certain this is a distinct defect
> - **\[S]** Skip — don't submit this finding"

Execute the chosen action:

- **R:** `gh api -X POST /repos/{repo}/issues/{N}/reactions -f content='+1'`
- **C:** Same reaction call, then `gh issue comment {N} --body "{minimal env+delta body}"`. The delta body is the Environment table plus ONE sentence describing what's different from the original. No session narrative.
- **N:** Proceed to step 5a-ii.
- **S:** Record nothing.

Record the outcome to the seen-cache under the fingerprint with fields `{action, issue_url, date}`.

**5a-ii. If no matching open issue exists** — create a new issue:

For each confirmed finding, create a GitHub issue:

**First, ensure the `{fp}` label exists** — it is per-fingerprint, so the first reporter of any defect is always creating a brand-new label. `gh issue create --label fp-XXXX` hard-fails if the label is missing, so guard it:

```
gh label create "{fp}" --repo {healthCheckRepo} \
  --color "ededed" \
  --description "Health-check fingerprint dedup key" 2>/dev/null || true
```

The `|| true` makes this idempotent: if the label already exists (second reporter of the same defect whose prior issue was closed, racing a parallel submission, etc.), `gh label create` exits non-zero and we proceed unharmed. The other labels in the command below (`health-check`, `workflow-improvement`, `bug`/`friction`/`gap`) are pre-created repo labels and do not need this guard.

**Then create the issue:**
```
gh issue create \
  --repo {healthCheckRepo} \
  --title "[health-check][{severity}][{fp}] {workflow}: {short description}" \
  --label "health-check,workflow-improvement,{severity},{fp}" \
  --body "{formatted body using issue template structure}"
```

When sub-step 2 returned `regression`, append ` — REGRESSION` to that `--title` value, after `{short description}`, and include the `## Regression` backlink section in the body. The command above is the literal one you run, so the marker has to be in it: an instruction that the title should say REGRESSION loses to a copied command that does not.

The fingerprint `{fp}` appears in both title (human-readable) and label (server-side filterable). Maintainers can query all reports for a defect via the `fp-*` label without relying on title text.

After the issue is created, write the fingerprint → issue-url mapping to the seen-cache at `{seenCachePath}` so this user does not re-report it while that issue stays open.

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
`src/skf-{workflow}/references/step-NN-name.md`

## Severity
`{bug | friction | gap}`
<!-- bug: instructions were wrong or contradictory -->
<!-- friction: instructions worked but caused back-and-forth or guessing -->
<!-- gap: a scenario arose that wasn't covered at all -->

## Fingerprint
`{fp}`
<!-- Deterministic dedup key: sha1(severity|workflow|step_file|section-slug)[:7]. -->
<!-- Also applied as a label so maintainers can filter all variants server-side. -->

## Finding
<!-- ONE sentence. What is the problem? Do not explain why yet. -->
{e.g. Step-05 forbids writes to `skills/` but does not name a staging directory.}

## Expected
<!-- ONE sentence. What did the step instruct or imply should happen? -->
{e.g. The step should name the staging directory between assembly and final write.}

## Actual
<!-- ONE sentence. What did you observe instead? -->
{e.g. No staging path specified, so artifacts were written to `skills/{name}/` and step 7 had to reorganize them.}

## Evidence
<!-- Bulleted `file:line` citations. 2-5 bullets. No narrative prose. -->
- `path/to/file.md:17` — "quoted text from the file"
- `path/to/other.md:62` — brief note on what it shows

## Impact
<!-- ONE sentence. What did this cost in THIS session? -->
{e.g. 50KB of artifacts written to the wrong path; step 7 required a file-move pass.}

## Suggested Fix
<!-- ONE recommended change. 1-3 sentences. Do NOT list multiple options here. -->
{e.g. Add a rule to step 5 naming `_bmad-output/{skill-name}/` as the staging directory used by step 6 validation.}

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

### 5b. On success, update the seen-cache

After each successful `gh issue create`, append to `{seenCachePath}`:

```json
{
  "fp-XXXXXXX": {
    "issue_url": "https://github.com/.../issues/123",
    "action": "created",
    "date": "YYYY-MM-DD"
  }
}
```

Ensure the parent directory exists. This file is global across the user's machine — not per-project — so the same defect is not re-reported across different repos the user works in while its issue stays open.

**Merge, never replace.** Read the existing file, set this one key, write the whole object back. A write that emits only the new key silently discards every other fingerprint the user has ever recorded.

**Read before you write, and never downgrade a `resolved` record.** Before setting the key, check whether one already exists with `"action": "resolved"`. If it does, and you are here because that resolved defect just recurred, you are recording the regression's new issue: overwrite it with `created` and the new URL, which is correct because a live issue now tracks the recurrence. In every other case leave a `resolved` record alone. The record must never move from `resolved` back to a suppressing action without a new open issue to justify it, or the next run silently re-arms the suppression the fix removed.

**The `action` vocabulary is `created`, `reacted`, `commented`, `resolved`.** The first three are written by this workflow. `resolved` is written by hand when the defect is fixed, and it is the only one that does not suppress. See the health-check section of `CONTRIBUTING.md` for when to record it.

### 5c. Local-Queue Path (gh unavailable OR friction/gap default)

For findings that didn't go live (gh unavailable, user declined the friction/gap opt-in, or user chose **\[S]** at the dedup gate), write a local file to `{localFallbackFolder}/`:

**Filename:** `hc-{workflow}-{timestamp}.md` (one file per finding, timestamp as YYYYMMDD-HHmmss)

**File content:** Same structured format as the issue body above, with YAML frontmatter:

```yaml
---
type: workflow-health-finding
workflow: {workflow name}
step_file: {step file path}
severity: {bug | friction | gap}
fingerprint: {fp-XXXXXXX}
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
- Severity gate respected: only `bug` submits live by default; `friction`/`gap` require explicit opt-in
- Fingerprint computed deterministically and applied to both title prefix and `fp-*` label
- `fp-*` label is ensured idempotently (`gh label create ... || true`) before `gh issue create`, so a first reporter of a defect never hard-fails
- Remote dedup search performed before every live submission; existing issues get reactions/delta-comments rather than duplicates
- Seen-cache at `{seenCachePath}` updated after every submission/reaction and consulted before every search
- Local fallback files written with clear manual submission instructions (when `gh` unavailable)
- Workflow ends cleanly

### SYSTEM FAILURE:

- Fabricating issues that were not actually encountered during the session
- Reporting vague issues without step file citations ("the workflow was confusing")
- Skipping the user review gate
- Creating issues without user confirmation
- Creating a new issue when a matching `fp-*` open issue already exists (without explicit user \[N] override)
- Submitting `friction` or `gap` findings live without the explicit severity-gate opt-in
- Using LLM-judged "similarity" in place of the deterministic fingerprint
- Not updating the seen-cache, causing the same user to re-report identical fingerprints
- Not providing the local fallback when `gh` is unavailable
- Continuing to load steps after this one (this is terminal)

**Master Rule:** Honesty is the only policy. Zero findings is the expected, healthy outcome. Fabricating issues to appear thorough undermines the entire self-improvement system and constitutes SYSTEM FAILURE.
