---
name: 'health-check'
description: 'Workflow self-improvement health check — captures real friction as GitHub issues'
# No nextStepFile — this is always the terminal step
healthCheckRepo: '{health_check_repo}'
localFallbackFolder: '{forge_data_folder}/improvement-queue'  # forge workspace artifact — use forge_data_folder (single, unambiguous SKF var), NOT output_folder (a Core Config var that resolves differently across co-installed BMad modules)
seenCachePath: '$HOME/.skf/health-check-seen.json'
seenCacheProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-health-check-seen.py'
  - '{project-root}/src/shared/scripts/skf-health-check-seen.py'
liveSubmitSeverities: ['bug']  # friction/gap go local-queue-default with explicit opt-in
---

# Health Check: Workflow Self-Improvement

> **Path convention:** This file is referenced as `shared/health-check.md` from workflow step frontmatter. All `shared/` paths resolve relative to the SKF module root (`_bmad/skf/` when installed, `src/` during development), not relative to the calling step file.

## STEP GOAL:

Reflect on the workflow that just completed. If real friction, bugs, or gaps were encountered in the SKF workflow instructions, capture them as structured findings for the user to review and optionally submit as GitHub issues.

**Zero overhead for clean runs.** If nothing went wrong, say so (or, on an envelope-only run, display only the setup envelope — see §0) and exit immediately.

## MANDATORY EXECUTION RULES:

### Universal Rules:
- Read the complete step file before taking any action
- Speak in `{communication_language}`

### Findings Rule:
Zero findings is the expected outcome of a good run. Report only a bug, friction or gap you hit in this session, each with the step file and section where it happened, and leave out anything you cannot tell apart from your own confusion: a finding you invent can become a real GitHub issue filed against the module.

---

## MANDATORY SEQUENCE

### 0. Announce Arrival

**Envelope-only runs.** Treat `{quiet_mode}` as true only when the workflow that loaded this step is skf-setup and it set `{quiet_mode}` to true. In every other case (unset, another workflow ran, or the user asked for this health check directly) treat it as false. skf-setup sets it under `--quiet` or in headless mode because its result envelope must be the only line setup displays. When it is true, this whole step displays nothing of its own and writes no text between tool calls: skip this announcement and its headless log, and queue any findings locally through **[Q]** without presenting them (§3, §4). Wherever it stops (the clean-run stop in §2, or the end of §5c), it displays skf-setup's `{setup_envelope_line}` verbatim after every tool call, with no code fence and nothing of this step's own before or after it (nothing at all if that line is empty). In a standalone setup run that line is the final message, because `claude -p` prints only the final message. When `{pipeline_mode}` is true, skf-setup is one step of a forger pipeline: control then returns to the forger, which keeps chaining.

**Result envelope line.** Any other workflow may bind `{result_envelope_line}` before it loads this step, in headless mode only (Brief Skill also in an `[auto]` run), to the result envelope line its run printed through the shared emitter (its `SKF_<NAME>_RESULT_JSON: ...` line; skf-test-skill's report step binds its `SKF_TEST_RESULT_JSON` line). When it is bound and not empty, wherever this step stops (the clean-run stop in §2, or the end of §5c) it displays that line verbatim as its very last line, after everything else it displays, with no code fence and nothing after it. In a standalone headless run, such as `claude -p`, which prints only the final message, that line is then the final message a pipeline reads. A workflow that binds nothing gets nothing extra.

**Display in `{communication_language}`:**

"**Running a quick self-improvement check on this workflow.** If nothing rough came up, I'll close out immediately."

**GATE [default: skip]** — If `{quiet_mode}` is true: skip the display and log nothing. Otherwise, if `{headless_mode}`: skip the display entirely, log: "headless: skipped health-check arrival announcement".

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

If `{quiet_mode}` is true, display only `{setup_envelope_line}` (§0). Otherwise display:

"**Health Check: Clean run.** No workflow issues to report.

Workflow complete."

When `{result_envelope_line}` is bound (§0), display it verbatim after that, as the last line.

**STOP HERE. Do not proceed further. The workflow is done.**

### 3. Present Findings (Only If Issues Exist)

**If `{quiet_mode}` is true:** do not present the findings. Go to §4, which chooses **[Q]** without displaying anything, so every finding, whatever its severity, is written to the local queue per §5c and nothing is submitted to GitHub.

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
| **Defect Key** | `{defect-key}`: one to four lower-case words naming the thing the fix would change (§5a sub-step 1) |
| **Fingerprint** | `fp-{7-hex}`: first 7 hex chars of `sha1("{severity}|{workflow}|{step_file}|{section-slug}|{defect-key}")`, from §5a sub-step 1's `fingerprint` call (`N/A` when SKF's health-check helper is missing) |

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

**GATE [default: Q]** — If `{quiet_mode}` is true, choose **[Q]** without displaying anything. Otherwise, if `{headless_mode}` is true, choose **[Q]** and log: "headless: queued {N} finding(s) locally". In both cases skip the question below and go to Menu Handling: live submission always needs an interactive **[Y]**.

**If interactive:** after presenting all findings, ask:

"**Submit these findings?**

- **[Y]** Yes — submit all findings
- **[N]** No — discard all findings
- **[E]** Edit — let me revise before submitting
- **[Q]** Queue locally — save every finding to {localFallbackFolder}/, submit nothing

_You are the final filter. Reject any finding that doesn't reflect a real issue you observed._"

**HALT and wait for user input.**

#### Menu Handling:

- **IF Y:** Proceed to step 5
- **IF N:** Display "Findings discarded. Workflow complete." — STOP
- **IF E:** Let user specify which findings to keep, modify, or remove. Then re-present the revised list and ask again.
- **IF Q:** Compute each finding's fingerprint as §5a sub-step 1 describes, then write every finding, whatever its severity, to the local queue per §5c — STOP after §5c

### 5. Route Each Finding by Severity

Before any submission, route each confirmed finding by severity:

- **`bug`** → live-submit path (step 5a below). High signal, priority for maintainers.
- **`friction`** / **`gap`** → local-queue by default (step 5c below). These are the most subjective categories and produce the most near-duplicates. Ask the user once per session: *"Also submit the {N} friction/gap finding(s) as GitHub issues? \[y/N]"* — only if the user affirms explicitly, route them through 5a.

A friction or gap finding that stays local still gets its fingerprint: compute it as §5a sub-step 1 describes, as **IF Q** does, then write it to the local queue per §5c.

### 5a. Live-Submit Path: Compute Fingerprint and Dedup

For each finding routed to live-submit:

**1. Compute the fingerprint**, a deterministic 7-hex dedup key, and the legacy fingerprint that sub-steps 2 and 4 fall back on, with SKF's health-check helper. Resolve `{seenCacheHelper}` from `{seenCacheProbeOrder}`; first existing path wins. The helper computes both fingerprints, looks them up in the seen-cache (sub-step 2) and records each outcome there (§5a-i, §5b), so neither fingerprint is hashed by hand and `{seenCachePath}` is never read or written by hand. If no candidate exists, give each finding the fingerprint `N/A`, and send every finding that §4 does not discard to the local queue (§5c) with the missing-helper reason instead of submitting it: there is no fallback.

Run it once per finding, with that finding's values:

```
uv run {seenCacheHelper} fingerprint --severity "{severity}" --workflow "{workflow}" --step-file "{step_file}" --section "{section-slug}" --defect-key "{defect-key}"
```

It prints `{"fp": "fp-XXXXXXX", "legacy_fp": "fp-XXXXXXX"}`. `{fp}` is `fp-` and the first 7 hex characters of `sha1("{severity}|{workflow}|{step_file}|{section-slug}|{defect-key}")`, and `{legacy_fp}` the same hash without `|{defect-key}`.

The `section-slug` is a kebab-case normalized section heading (e.g. `missing-staging-path`). Never include line numbers — they drift when files are edited.

The `defect-key` names the defect itself, so two different defects in one section get two fingerprints while two reports of one defect that name the same thing get the same one. It is one to four lower-case ASCII words joined by hyphens that name the thing the fix would change, in the step file's or the code's own words: a function, a script subcommand, a field, a flag, a rule's term or a section's concept. Pick the most specific name the fix would edit. To turn a name into the key, drop its leading dashes and underscores, split it at spaces, underscores, hyphens, dots and each lower-case letter followed by an upper-case one, drop every character of each word that is not an ASCII letter or digit, lower-case each word and join them with hyphens (`composeStories` gives `compose-stories`, `reader's own code` gives `readers-own-code`); a name of more than four words keeps its last four. When the defect is a missing rule, there is no name to copy yet: name the case the rule should cover in two to four of the step file's own words, the noun the rule would be about, then what makes the case distinct. A wrong check in `floor_check` gives `floor-check`, a misread `--orphan-action` flag gives `orphan-action`, and a missing rule for a `const` holding a function, in a step file whose rule covers a `const` holding a component, gives `const-holding-function`. Never use a line number, a file name or path (the step file already says where), a severity, or words from this session's own story: whoever reports the same defect next must reach the same key from the source alone. Never use the section's own subject alone either: every defect in the section shares it.

`legacy_fp` is the section fingerprint, the fingerprint without the key, which every defect of one severity in one section shares. Issues and seen-cache records made by an SKF version without the key carry it as their fingerprint, and every issue this step files records it in its body (§5a-ii), so a match on it is only ever a possible match (sub-steps 2 and 4).

A value that breaks its rule makes the call exit 2 and print one `{"status": "error", "message": ...}` line on stderr that names the rule: a severity other than `bug`, `friction` or `gap`, a section slug that is not kebab-case, a defect key that is not one to four such words, or a workflow or step file that is empty or holds `|` or a line break. Fix that value by its rule and run the call again. A call that prints no JSON on stdout and no such line on stderr did not run the helper (uv or Python could not start it, and uv's own errors exit 2 as well): treat it as a missing helper, so the finding gets the fingerprint `N/A` and goes to the local queue (§5c) with the missing-helper reason.

**2. Check the local seen-cache** at `{seenCachePath}`:

```
uv run {seenCacheHelper} lookup --fp "{fp}" --legacy-fp "{legacy_fp}"
```

It prints `{"verdict": ..., "record": ..., "matched_on": ...}`: the verdict, the record it came from, which the treatments below read, and whether that record sits under `{fp}` or `{legacy_fp}` (`record` and `matched_on` are null when there is none). The helper reads the file itself, and a missing, empty or corrupt cache is an empty one. If the call fails or prints no JSON, continue as `unseen`: this check never halts a run.

**Presence in the cache is not the verdict.** A fingerprint whose defect was already fixed must NOT suppress: a fresh sighting of a fixed defect is a *regression*, and it is the single most valuable report this loop can produce. The helper looks up `{fp}`, and only when the cache has no record for it, `{legacy_fp}`, then works its branches on the record found. For a record with the action `created`, `reacted` or `commented` and an issue URL, it asks the issue itself through `gh issue view`, stopped after 10 seconds: the cache is machine-local and records only what *this* user did, while the issue's state is shared, so it is the better authority. Act on the `verdict` it prints:

- `unseen`: no record under either fingerprint, or a record found only under `{legacy_fp}` (`matched_on` is `legacy_fp`) that would have suppressed. That record was written by an SKF version without the defect key, and every defect of this severity in this section shares its fingerprint, so it may be another defect's: log `"{fp}: legacy record {legacy_fp} may be another defect, reporting"`, and sub-step 4 still offers its issue while that issue is open. Go to sub-step 3.
- `handled`: a record under `{fp}` whose issue is open, was closed as not planned (how the dedup Action closes a duplicate and a maintainer closes a wontfix, neither of them a fix) or could not be checked (offline, no `gh`, the time limit, a deleted issue), or one with no issue URL. Skip the finding, as the next paragraph says.
- `regression`: a record under `{fp}` marked `resolved` by hand when the defect was fixed, or whose issue was closed as completed (or whose pull request was merged). Go to sub-step 3 and apply the regression treatment below.
- `possible-regression`: the same, found only under `{legacy_fp}`, so what was fixed may be another defect in this section. Go to sub-step 3 and apply the possible-regression treatment below.
- `unrecognized`: a record with no `action` or one this file does not write, hand-edited or written by a newer version of this file, so it cannot be confirmed handled. Go to sub-step 3 as an ordinary submission.

**`handled` is the only verdict that suppresses.** Skip submission silently and log: `"fp-{hash}: already handled on {date}, issue {url} — skipping"`. Every other verdict proceeds to sub-step 3.

**Why anything uncertain reports instead of suppressing.** A duplicate report is self-healing: the dedup Action closes it and moves the upvote to the canonical issue. A silenced regression is caught by nothing at all. When the verdict is in doubt, report.

**Regression treatment** (verdicts `regression` only). Carry the prior record forward so the recurrence can never be filed as a first sighting:

- Append ` — REGRESSION` to the issue title, after `{short description}`.
- Add a `## Regression` section immediately above `## Finding`, containing one line: `Regression of {issue_url}, resolved {date}.` If the prior record has no `issue_url`, write `Regression of a previously resolved local finding, resolved {date}.` The `{fp}` label still ties the two together server-side.
- Leave `## Finding` and the other one-sentence sections exactly as specified below. The backlink lives in its own section precisely so those budgets are untouched.

**Possible regression** (verdict `possible-regression` only). The resolved record was found under `{legacy_fp}`, so what was fixed may be another defect in this section. Add the same `## Regression` section, with one line: `Possibly a regression of {issue_url}, resolved {date}: that report's fingerprint has no defect key, so it may be another defect in this section.` If the prior record has no `issue_url`, write `Possibly a regression of a previously resolved local finding in this section, resolved {date}.` Leave the title unmarked, since this record cannot prove a recurrence. The two reports carry different `fp-*` labels, so this line is their only link.

**What this does and does not catch.** The fingerprint is `sha1` over the section slug and the defect key, so a fix that renames or relocates the section it touches, or renames the thing the key names, changes the fingerprint. So does a report that names the same defect by another thing than an earlier report did: independent reports of one defect often pick different keys. Such a report arrives as `unseen` and is reported as a first sighting, which is safe but unlinked here; once it is filed, the dedup Action flags it (§5a-ii). These branches catch the regressions that recur under the same heading in the same step file, under the same key, which is the case where the old behaviour was silent.

**3. Check GitHub CLI availability** with `gh auth status`. If `gh` is unavailable, fall through to step 5c (local fallback).

**4. Remote dedup search**: one deterministic call, and a second only when the first finds nothing:

```
gh search issues --repo {healthCheckRepo} --state open "{fp} in:title" --json number,url,title --limit 1
```

An issue it finds reports this defect. When it finds none, search once more, for the section fingerprint in titles and bodies:

```
gh search issues --repo {healthCheckRepo} --state open "{legacy_fp} in:title,body" --json number,url,title --limit 5
```

Each issue this second search finds is a possible match: it was filed by an SKF version whose fingerprints carry no defect key, or it reports a defect of this severity in this section under another defect key. Every defect of this severity in this section shares that fingerprint, so the user decides at 5a-i.

**5a-i. If a matching open issue exists:**

Present to user:

> "**Matching report found:** #{N} — {title}
>
> Your finding has the same fingerprint `{fp}`. Options:
> - **\[R]** React (👍) on the existing issue — silent upvote, adds no comment
> - **\[C]** React + comment with YOUR environment/evidence delta (use only if it materially differs from the original)
> - **\[N]** Create a new issue anyway — only if you're certain this is a distinct defect
> - **\[S]** Skip — don't submit this finding"

**Possible matches.** When the issues were found by `{legacy_fp}`, list each one and present the same options under this opening instead:

> "**Possible match:** #{N}: {title} (one line for each issue found)
>
> It carries this section's fingerprint `{legacy_fp}`, which every `{severity}` finding in this section shares: it was filed by an SKF version whose fingerprints carry no defect key, or it reports a defect in this section under another defect key, so it may report another defect. Pick **\[R]** or **\[C]** only if it reports this one, naming it when more than one is listed, and **\[N]** if none does. Options:"

Only the user decides a possible match. A headless run never reaches this choice, because §4 queues its findings locally without a search. A run that reaches it with no user to ask takes **\[S]**, so the finding goes to the local queue (§5c) with the possible-match reason, and nothing is posted on a guess.

Execute the chosen action:

- **R:** `gh api -X POST repos/{healthCheckRepo}/issues/{N}/reactions -f content='+1'`
- **C:** Same reaction call, then `gh issue comment {N} --repo {healthCheckRepo} --body-file "{localFallbackFolder}/bodies/{fp}-{timestamp}.md"`. The delta body is the Environment table plus ONE sentence describing what's different from the original. No session narrative. Write it to that file with the Write tool before the reaction, as **Pass each body as a file** in §5a-ii says.
- **N:** After a match found by `{fp}`: the open issue carries this same fingerprint, so a new issue under it would be closed as its duplicate. Choose a more specific defect key that names what sets this defect apart (the more specific name the fix edits, or the case it covers, still in the source's words), recompute `{fp}` with it, then proceed to step 5a-ii. After a possible match, proceed to step 5a-ii as is: that issue's `fp-*` label differs from `{fp}`.
- **S:** Record nothing.

The **R** and **C** calls name `{healthCheckRepo}`, as the step's other issue calls do: without it, `gh` reacts or comments on the repository of the folder the workflow ran in, usually the user's own project. If one of them exits non-zero, log its stderr message and make no further call for this finding: **C** posts no comment after a failed reaction, and a reaction it already added stays. Record nothing (run neither record call below) and write the finding to the local queue (§5c) with the failed-submission reason. When **C** fails, its body file stays in `{localFallbackFolder}/bodies/`, its name starting with the `fingerprint` the queued finding records.

When every call of **R** or **C** succeeded, record the outcome under `{fp}`, also when the match was found by `{legacy_fp}`: `reacted` after **R** and `commented` after **C**, with the matched issue's `url` and today's date as YYYY-MM-DD:

```
uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" --date "{today}"
```

When sub-step 2 returned `regression`, run this one instead: **R** or **C** says this open issue reports the defect, so it now tracks the recurrence and replaces the `resolved` record the fix left under `{fp}`.

```
uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" --date "{today}" --regression
```

**S** records nothing, and **N** records its new issue in §5b. Read what the call prints as §5b says; if it fails, log its stderr message and go on.

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
  --body-file "{localFallbackFolder}/bodies/{fp}-{timestamp}.md"
```

**Pass each body as a file.** Before the label call above, write the issue body (the format below) with the Write tool to a file of its own, `{localFallbackFolder}/bodies/{fp}-{timestamp}.md`, `{timestamp}` being the time of the write as YYYYMMDD-HHmmss; **C** writes its comment body the same way. The body quotes paths, evidence and its `Section fingerprint:` line in backticks: on the command line, inside double quotes, the shell would run each backticked span or `$(...)` as a command and put its output in its place, and a double quote in it would end the argument. So a body never goes on the command line, and the file is never written through the shell (`echo`, `printf` or a heredoc), which can expand it the same way. If the Write fails, make no call for this finding: log the error and write the finding to the local queue (§5c) with the failed-submission reason. The title does stay on the command line, so write `{short description}` with no backtick, `$`, double quote or backslash. The file stays after the call, in `bodies/` apart from the findings the queue holds, as the record of what was sent or tried; a later post writes a new one.

When sub-step 2 returned `regression`, append ` — REGRESSION` to that `--title` value, after `{short description}`, and include the `## Regression` backlink section in the body. The command above is the literal one you run, so the marker has to be in it: an instruction that the title should say REGRESSION loses to a copied command that does not.

A `possible-regression` gets its `## Regression` section and no title marker.

The fingerprint `{fp}` appears in both title (human-readable) and label (server-side filterable). Maintainers can query all reports for a defect via the `fp-*` label without relying on title text.

The dedup Action reads the body's `Section fingerprint:` line too. When the new issue matches no open issue's fingerprint but another open health-check issue records the same section fingerprint under a different defect key, or was filed without a key and carries it as its label, the Action comments with a link to each such issue and adds the `possible-duplicate` label. It closes nothing on that match: two reports of one defect can name it by different keys, and every defect of one severity in one section shares the section fingerprint, so a maintainer decides.

After the issue is created, record it under `{fp}` as §5b says, so this user does not re-report it while that issue stays open.

If `gh issue create` exits non-zero, log its stderr message and record nothing: §5b runs only after a create that succeeded, so after a `regression` verdict the `resolved` record stays. Write the finding to the local queue (§5c) with the failed-submission reason, as a failed reaction or comment is: its queue file holds the text of its body file under the §5c frontmatter, so what failed to post is what waits to be submitted.

**Writing rules — non-negotiable:**

- **One issue per finding.** If you observed two independent problems, submit two issues.
- **Respect the length budgets.** Finding, Expected, Actual, Impact are each ONE sentence. Evidence is 2-5 bullets, not prose. Suggested Fix is 1-3 sentences with ONE recommendation — multiple options go in the `Alternatives considered` collapsible or (better) not at all.
- **Quote, don't paraphrase.** In Evidence, cite the exact `file:line` and put the quoted text in quotes. Link the convention to the instruction that caused it.
- **Never narrate the session.** The reader wants the defect, not the story. If a sentence starts with "During my run..." or "I was trying to...", delete it.

**Issue body format:**
```markdown
## Workflow
{workflow name, e.g. `skf-create-skill`}

## Step File
`src/skf-{workflow}/references/step-NN-name.md`

## Section
`{section-slug}`

## Severity
`{bug | friction | gap}`
<!-- bug: instructions were wrong or contradictory -->
<!-- friction: instructions worked but caused back-and-forth or guessing -->
<!-- gap: a scenario arose that wasn't covered at all -->

## Fingerprint
`{fp}`
<!-- Deterministic dedup key: sha1(severity|workflow|step_file|section-slug|defect-key)[:7], each as this issue writes it. -->
<!-- Also applied as a label so maintainers can filter all variants server-side. -->

Section fingerprint: `{legacy_fp}`
<!-- The same hash without the defect key, shared by every defect of this severity in this section. Body text only, never a label: the dedup Action reads it to flag possible duplicates. -->

## Defect Key
`{defect-key}`
<!-- One to four lower-case words naming the thing the fix would change, in the step file's or the code's own words. -->

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
{e.g. Add a rule to step 5 naming `_bmad-output/.skf-stage/{skill-name}/` as the staging directory used by step 6 validation.}

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

After creating all issues, display those that were created, `{N}` counting only them, unless none was (a create that failed is listed by §5c):

"**{N} issue(s) created on {healthCheckRepo}:**
{list each issue URL}"

**Closing line.** The step displays "Workflow complete." once, after everything else it displays but a bound `{result_envelope_line}` (§0). When any finding of this run goes to the local queue (§5c), display nothing more here: §5c writes its files, then ends its block with that line. Otherwise display "Workflow complete." now, after the block above, or alone when no issue was created because every finding was a reaction or a comment that posted (§5a-i).

### 5b. On success, update the seen-cache

After each successful `gh issue create`, record the new issue under `{fp}`, with the URL `gh issue create` printed and today's date as YYYY-MM-DD:

```
uv run {seenCacheHelper} record --fp "{fp}" --action created --issue-url "{new_issue_url}" --date "{today}"
```

This file is global across the user's machine, not per-project, so the same defect is not re-reported across different repos the user works in while its issue stays open.

When sub-step 2 returned `regression`, run this one instead: the new issue tracks the recurrence, so it replaces the `resolved` record the fix left under `{fp}`.

```
uv run {seenCacheHelper} record --fp "{fp}" --action created --issue-url "{new_issue_url}" --date "{today}" --regression
```

It prints `{"written": ..., "fp": ..., "record": ..., "set_aside": ...}`, `record` being what the cache now holds under `{fp}`: `{"issue_url": ..., "action": "created", "date": "YYYY-MM-DD"}`. If the call fails, log its stderr message and go on: a lost record costs at most a duplicate report, which the dedup Action closes. When `set_aside` is not null, after this call or §5a-i's, tell the user that `{seenCachePath}` did not parse, so it was renamed to that path and a new cache was started, and that they keep its records by fixing that file and copying its entries into `{seenCachePath}`.

**What the helper guarantees.** It merges, never replaces: it sets the `{fp}` key alone and keeps every other fingerprint the user has recorded. It writes under `{fp}` only: a record under `{legacy_fp}` stays exactly as it is, whatever its action, since it may be another defect's. It never downgrades a `resolved` record: without `--regression` it leaves one alone and prints `"written": false`, so a fixed defect's suppression never comes back without a new open issue to justify it. It holds `{seenCachePath}.lock` while it reads and writes, so parallel SKF sessions keep each other's records, and it renames a cache that does not parse to `{seenCachePath}.corrupt-<UTC time>` (its `set_aside`) instead of discarding the records in it.

**The `action` vocabulary is `created`, `reacted`, `commented`, `resolved`.** The first three are written by this workflow. `resolved` is written by hand when the defect is fixed, and it is the only one that does not suppress. See the health-check section of `CONTRIBUTING.md` for when to record it.

### 5c. Local-Queue Path (gh unavailable, friction/gap default, or Queue locally)

For findings that didn't go live (gh unavailable, SKF's health-check helper missing, user declined the friction/gap opt-in, user chose **\[S]** at the dedup gate, a run with no user to ask took **\[S]** at a possible match, a reaction or comment at the dedup gate failed, a new issue failed to post, or the §4 review gate resolved to **\[Q]**), write a local file to `{localFallbackFolder}/`:

**Filename:** `hc-{workflow}-{timestamp}.md` (one file per finding, timestamp as YYYYMMDD-HHmmss; when findings share a timestamp, append `-2`, `-3`, … to the later names so no file is overwritten)

**File content:** Same structured format as the issue body above, with YAML frontmatter (for a create that failed, that body is the text of its body file in `{localFallbackFolder}/bodies/`, unchanged):

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

When SKF's health-check helper is missing (§5a sub-step 1), write `N/A` as the `fingerprint` here and in the body's `## Fingerprint` and `Section fingerprint:` lines.

After writing all files, if `{quiet_mode}` is true, display only `{setup_envelope_line}` (§0) and stop. Otherwise display the block below. `{reason}` is the sentence that says why the findings stayed local: "GitHub CLI is not available.", "SKF's health-check helper is missing; re-install SKF to submit these.", "Friction and gap findings stay local unless you opt in.", "You skipped these at the dedup gate.", "These may match an open issue from the same section; review them before submitting." (the possible-match reason), "Posting these to GitHub failed." (the failed-submission reason) or "The review gate queued these locally."

"**{N} finding(s) saved locally:**
{list each file path}

{reason} To submit these as issues, run:
`gh issue create --repo {healthCheckRepo} --title \"[title]\" --body-file {file-path}`

Or open them manually at: <https://github.com/{healthCheckRepo}/issues/new/choose>

Workflow complete."

When `{result_envelope_line}` is bound (§0), display it verbatim after that block, as the last line.
