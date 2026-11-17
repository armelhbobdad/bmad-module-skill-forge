---
name: 'health-check'
description: 'Workflow self-improvement health check — captures real friction as GitHub issues'
# No nextStepFile — this is always the terminal step
healthCheckRepo: '{health_check_repo}'  # §0 reads it raw; §3's settings call checks it
healthCheckAutosubmit: '{health_check_autosubmit}'  # §3's settings call reads it; off without a helper
localFallbackFolder: '{forge_data_folder}/improvement-queue'  # SKF's own folder: output_folder resolves differently across co-installed BMad modules
seenCachePath: '$HOME/.skf/health-check-seen.json'
seenCacheProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-health-check-seen.py'
  - '{project-root}/src/shared/scripts/skf-health-check-seen.py'
  - 'shared/scripts/skf-health-check-seen.py'
liveSubmitSeverities: ['bug']  # what [Y] and an autosubmit headless run submit; [A] submits every severity
---

# Health Check: Workflow Self-Improvement

> **Path convention:** This file is referenced as `shared/health-check.md` from workflow step frontmatter. All `shared/` paths resolve relative to the SKF module root (`_bmad/skf/` when installed, `src/` during development), not relative to the calling step file.

## STEP GOAL:

Reflect on this session since the last health check that ran in it, and capture the bugs, friction and gaps you hit in SKF's own instructions as findings for the user to review and optionally submit as GitHub issues.

**Zero overhead for clean runs.** If nothing went wrong, say so and exit immediately.

## MANDATORY EXECUTION RULES:

### Universal Rules:
- Read the complete step file before taking any action
- Speak in `{communication_language}`

### Findings Rule:
Zero findings is the expected outcome of a good run. Report only a bug, friction or gap you hit in this session since its last health check, each with the step file and section where it happened, and leave out anything you cannot tell apart from your own confusion: a finding you invent can become a real GitHub issue filed against the module. Leave out too any finding an earlier check in this session already showed, queued or filed.

---

## MANDATORY SEQUENCE

### 0. Announce Arrival

**Result envelope line.** A workflow may bind `{result_envelope_line}` before it loads this step, in a headless run, to the result envelope line its run printed. When it is bound and not empty, wherever this step stops (the off switch below, the clean-run stop in §2, the stop when no finding survives §3, **\[N]** at the review gate in §4, the closing line of §5a-ii, or the end of §5c) it displays that line verbatim as its very last line, with no code fence and nothing after it. In a standalone headless run, such as `claude -p`, that line is then the final message a pipeline reads.

**Off switch.** Before anything else, read `health_check_repo` in `{project-root}/_bmad/skf/config.yaml` yourself: a workflow binds only its own config keys. When the key is there and empty (`''`, `""`, nothing or only a comment after its colon, or a YAML null such as `~` or `null`), the health check is off: display the two lines below, then, when `{result_envelope_line}` is bound, that line verbatim, as the last line, and STOP: announce nothing and reflect on nothing.

"**Health Check: off.** `health_check_repo` is empty in `_bmad/skf/config.yaml`, so nothing was reviewed or sent.

Workflow complete."

Otherwise `{healthCheckRepo}` is that value, or `armelhbobdad/bmad-module-skill-forge` when the key or the file is absent, until §3's `settings` call checks it.

**Display in `{communication_language}`:**

"**Running a quick self-improvement check on this workflow.** If nothing rough came up, I'll close out immediately."

**GATE [default: skip]**: if `{headless_mode}`, skip the display entirely, log: "headless: skipped health-check arrival announcement".

**If interactive:** display the line above, then go on to §1 without waiting.

### 1. Reflect on the Run

Silently review this session, from the end of the last health check in it that was not off (its start when none did; for a check run on request, the start of the workflow it is run for), for each point where an SKF instruction you were following was wrong or contradictory (`bug`), worked but left you guessing or going back and forth with the user (`friction`), or was silent on a case you hit (`gap`). If there is none, close the clean run (§2); otherwise go on to §3.

### 2. Close a Clean Run

Display:

"**Health Check: Clean run.** No workflow issues to report.

Workflow complete."

When `{result_envelope_line}` is bound (§0), display it verbatim after that, as the last line. Stop: the workflow is done.

### 3. Draft Each Finding (Only If Issues Exist)

Every finding, whatever its route, gets its fingerprints, its title and its issue body on disk before anyone reviews it, so the review gate (§4), `gh` (§5a-ii) and the local queue (§5c) all use one draft.

**A defect in this step.** A defect in this file's own instructions, or in the helper or a `gh` command it runs, that bites while this step runs is a finding about the health check itself: its workflow is `health-check` and its step file `shared/health-check.md`. It is never posted (§4). Take at most one per check: name, fingerprint and draft it as below, also when it bites after the review gate, and queue it (§5c) with §4's reason. Display any further one only as a one-line note, `Health check note: {what bit}, in shared/health-check.md "{section heading}".`, and draft nothing for it.

**Resolve the helper.** Resolve `{seenCacheHelper}` from `{seenCacheProbeOrder}`; first existing path wins. Its last entry resolves from the SKF module root (the path convention above), where a plugin install keeps it. Never hash a fingerprint or read or write `{seenCachePath}` by hand: the helper does both. If no candidate exists, give each finding the fingerprint `N/A`, write its draft by hand as **Write the draft** says, and send every finding that §4 does not discard to the local queue (§5c) with the missing-helper reason: there is no fallback.

**Read the settings.** With a helper, run once:

```
uv run {seenCacheHelper} settings --config "{project-root}/_bmad/skf/config.yaml"
```

It prints `{"repo_state", "repo", "host", "owner_repo", "is_default", "autosubmit"}`. From here on `{healthCheckRepo}` is its `repo`, `{healthCheckHost}` its `host`, `{healthCheckOwnerRepo}` its `owner_repo` and `{healthCheckAutosubmit}` its `autosubmit`, which is off without a helper. On `off`, display §0's two off lines, then the bound `{result_envelope_line}`, and STOP, drafting nothing. On `invalid`, `{healthCheckRepo}` is no repository: display "**Health Check:** `health_check_repo` is `{repo}` in `_bmad/skf/config.yaml`, which is not OWNER/REPO or HOST/OWNER/REPO, so no finding will be submitted.", run no `gh` call, and send every finding to the local queue (§5c) with the no-repository reason. A call that fails or prints no JSON leaves the helper missing.

**A refused call.** A call the session refuses never ran (a permission prompt answered no, or a headless run with no rule that allows it), so a refused helper call (any `uv run` of `{seenCacheHelper}`) is no missing helper and a refused Write no failed one. After the session refuses a helper call or a Write of this step, make no further helper call, Write or `gh` call in this check, and send every finding not yet submitted to the local queue (§5c) with the refused reason. A refusal before the review gate skips §4 and §5: go straight to §5c. A refused `gh` call is §5a sub-step 2's.

**Name the step file, the section and the defect.** The step file is the `references/` file whose instruction bit, and `{workflow}` is the folder name of the workflow whose `references/` folder holds it: usually the workflow that just ran, and the other workflow for a step file loaded from its `references/`. The section is the heading of the innermost section of the step file that holds the instruction, copied exactly as the file writes it, numbering included. A bold run-in label (`**Foo.**`) is no heading: take the heading that encloses it. A defect in an instruction of the workflow's SKILL.md, of a script or of a `shared/references` file takes the step file that was running when it bit and the heading of that file's section that was running, or the file's H1 when none fits. A defect in what a workflow's own `references/health-check.md` does besides loading this step (Update Skill's, Quick Skill's and Verify Stack's) takes that file, its section found by the innermost-section rule above. The defect name is the thing the fix would change, in the step file's or the code's own words: a script by its file name, a function, a script subcommand, a field, a flag, a rule's term or a section's concept. Pick the most specific name the fix would edit, so two defects in one section get two fingerprints and two reports of one defect get one; the helper turns it into the defect key, one to four lower-case ASCII words (a longer name keeps its last four). When the defect is a missing rule, there is no name to copy yet: name the case the rule should cover in two to four of the step file's own words, the noun the rule would be about, then what makes the case distinct. A wrong check in `floor_check` gives `floor-check`, a misread `--orphan-action` flag gives `orphan-action`, and a missing rule for a `const` holding a function, in a step file whose rule covers a `const` holding a component, gives `const-holding-function`. Never use a path, a line number, a severity, or words from this session's own story: whoever reports the same defect next must reach the same key from the source alone. Never use the section's own subject alone either: every defect in the section shares it.

**Give it a short description**, one line naming the defect for its issue title, with no backtick, `$`, double quote, backslash or `!`: the title goes on the command line.

Write the two names and the description with the Write tool to `{localFallbackFolder}/bodies/names-{timestamp}-{i}.json`, `{timestamp}` being the time of the write as YYYYMMDD-HHmmss and `{i}` the finding's number, as the JSON object `{"section_heading": "<the heading>", "defect_name": "<the name>", "short_description": "<the description>"}` with each value JSON-escaped, so no quote in a name meets the shell. If the Write fails, or the shell says it cannot open that file, make no fingerprint call for this finding (a call that cannot read its names file prints no JSON, which does not mean the helper is missing): log the error, naming the finding, give the finding the fingerprint `N/A` and send it to the local queue (§5c) with the could-not-fingerprint reason. Otherwise run the helper once per finding, with that finding's severity, workflow and step file (its name, or any path to it):

```
uv run {seenCacheHelper} fingerprint --severity "{severity}" --workflow "{workflow}" --step-file "{step_file}" --stdin < "{localFallbackFolder}/bodies/names-{timestamp}-{i}.json"
```

It prints `{"fp", "legacy_fp", "tuple", "step_file", "section_slug", "defect_key", "title", "regression_title", "body_header"}`. `{legacy_fp}` is the section fingerprint, the same hash without the defect key, so a match on it is only ever a possible match. Use `{title}`, or `{regression_title}` after a `regression` verdict (§5a), exactly as printed wherever the finding's title appears. No `title` means the names file held no description: add it there and run the call once more. On exit 2 its stderr line names the value it refused: fix that value, or for a refused heading take the heading that encloses it (the file's H1 at the top), and run the call once more. Never loop: when that second call is refused too, log its message, naming the finding, give the finding the fingerprint `N/A` and send it to the local queue (§5c) with the could-not-fingerprint reason. JSON on neither stream means the helper did not run: treat it as missing (fingerprint `N/A`, missing-helper reason). Two findings that get one `{fp}` are one defect: merge them into one finding before drafting.

**Write the draft.** Write each finding's issue body (the format below) with the Write tool to a file of its own, `{localFallbackFolder}/bodies/{fp}-{timestamp}.md`, opening with the call's `body_header` exactly as printed: `{draft_path}` is its path from here on. Every route uses that file as it stands, and after the gate it changes only by a regression's `## Regression` section (§5a sub-step 1) or an **\[N]** re-key at the dedup gate (§5a-i). Never put a body on the command line or write it through the shell (`echo`, `printf` or a heredoc): the shell would run each backticked span or `$(...)` in it, and a double quote in it would end the argument. If the Write fails, log the error, naming the finding, and drop the finding: there is no text to show, post or queue.

A finding with the fingerprint `N/A` has no `body_header`: write its header by hand in the same form, with the workflow, the step file as `src/{workflow}/references/{file}.md` (`src/shared/health-check.md` for the health check itself), the section's heading as the step file writes it, the severity, `N/A` as the Fingerprint and in the `Section fingerprint:` line, and the defect name, each in backticks. Name its draft `{localFallbackFolder}/bodies/hc-{workflow}-{timestamp}-{i}-draft.md`, `{i}` being the finding's number, and its title `[health-check][{severity}][N/A] {workflow}: {short description}`.

With a helper, then check every draft, `N/A` included, and its title for the user's folders, which a public issue must never name:

```
uv run {seenCacheHelper} check-draft --body-file "{draft_path}" --title "{title}" --project-dir "{project-root}"
```

When it exits 2 with a message that names lines or the title holding the project's folder or the home folder, rewrite them, citing SKF's files by their module path (`src/skf-test-skill/references/report.md:12`), and run the call once more. A draft refused twice, or one the call could not check (any other exit 2, a failure or no JSON), goes to the local queue (§5c) with the unchecked-draft reason and is never posted.

When no finding survives this step, display "**Health Check:** no finding could be drafted, so nothing was reviewed or sent." and then "Workflow complete.", then, when `{result_envelope_line}` is bound, that line verbatim, as the last line, and STOP.

**Writing rules** (a maintainer triages the issue without this run in the room):

- **One issue per finding.** If you observed two independent problems, submit two issues.
- **Respect the length budgets.** Finding, Expected, Actual and Impact are one sentence each, Evidence two to five bullets, and the Suggested Fix one to three sentences with one recommendation.
- **Quote, don't paraphrase.** In Evidence, cite the exact `file:line` and put the quoted text in quotes.
- **Name nothing of the user's.** The title, every section of the body and a **C** comment describe SKF's instruction, never the user's work: they name no project, library, skill, file or path of the user's and no secret, and Evidence quotes only SKF's own files (its step files, SKILL.md files, shared files and scripts), never the user's project code, the source a skill was built from or a brief's or a skill's content: an issue on the default repository is public.
- **Write it in English.** The short description, the issue body and a **C** comment are in English whatever `{communication_language}`; the gate and every other display stay in `{communication_language}`, and a title, a draft or a comment is shown exactly as written.
- **Never narrate the session.** The reader wants the defect, not the story. If a sentence starts with "During my run..." or "I was trying to...", delete it.

**Issue body format:** the sections from `## Workflow` to `## Defect Key` are the `body_header` the fingerprint call printed, copied exactly as printed.
```markdown
## Workflow
`{workflow}`

## Step File
`{step_file}`

## Section
`{section-slug}`

## Severity
`{bug | friction | gap}`

## Fingerprint
`{fp}`

Section fingerprint: `{legacy_fp}`

## Defect Key
`{defect-key}`

## Finding
{e.g. Step 5 forbids writes to the skills output folder but does not name a staging directory.}

## Expected
{e.g. The step should name the staging directory between assembly and final write.}

## Actual
{e.g. The step wrote its artifacts straight to the skill's final folder.}

## Evidence
- `path/to/file.md:17`: "quoted text from the file"
- `path/to/other.md:62`: brief note on what it shows

## Impact
{e.g. 50KB of artifacts written to the wrong path; step 7 required a file-move pass.}

## Suggested Fix
{e.g. Add a rule to step 5 naming `_bmad-output/.skf-stage/{skill-name}/` as the staging directory used by step 6 validation.}

## Environment
| Field | Value |
|-------|-------|
| Date | {ISO date} |
| OS | {e.g. macOS 15.2, Ubuntu 24.04, Windows 11} |
| AI Editor | {e.g. Claude Code, Cursor, Windsurf} |
| Model | {e.g. Claude Opus 4.6, Claude Sonnet 4.6} |
| Forge Tier | {Quick/Forge/Forge+/Deep, else N/A} |
| Run Mode | {interactive or headless} |
| SKF Version | {the `version` the helper prints, below, else N/A} |
```

The `Section fingerprint:` line is body text only, never a label, since the dedup Action reads it to flag possible duplicates. Run Mode is `headless` when `{headless_mode}` is true, else `interactive`.

**SKF Version comes from the helper**, which reads the version of the SKF it belongs to, whatever the install, never from `{project-root}`:

```
uv run {seenCacheHelper} version
```

### 4. User Review Gate

**A finding about the health check itself.** A finding whose workflow is `health-check` (§3) is never posted. Every route that submits or queues it (**\[Y]**, **\[A]**, **\[Q]** and a headless run) writes it to the local queue (§5c) with the reason "Found in the health check's own instructions; review it before submitting.", which replaces any reason its route would give; **\[N]** discards it with the rest.

**GATE [default: Q]**: if `{headless_mode}` is true, skip the question below and choose by `{healthCheckAutosubmit}` (§3): while it is off, choose **[Q]**, with the reason "Headless runs queue every finding while health_check_autosubmit is off.", and log: "headless: queued {N} finding(s) locally"; when it is on, choose **[Y]**, which submits the bug findings, still deduped, and queues the friction and gap findings with the reason "Headless runs never submit friction or gap findings.", and log: "headless: autosubmit on, submitting bug findings only". Then go to Menu Handling.

**If interactive:** show every finding: for each one, its title (§3), the path of its draft and the draft's full text. Say that when the seen-cache finds the defect was fixed before, the draft gains a `## Regression` section above `## Finding`, and a confirmed regression the `REGRESSION: ` title (§5a sub-step 1). Say too that a finding about the health check itself is queued, never posted, whatever the user chooses but **\[N]**. When no finding can be submitted, because each one is about the health check itself or §3 sent it to the local queue, ask instead "**Queue these findings locally?**" with **\[Q]**, **\[N]** and **\[E]** only.

Then ask, saying "public issues" for "issues" when §3's `settings` call printed `is_default` true, and for any other repository adding "(public if that repository is public)" after its name:

"**Submit these findings as issues on {healthCheckRepo}, filed with your GitHub account?**

- **[Y]** Yes: submit the bug findings; friction and gap findings stay local
- **[A]** All: submit every finding, friction and gap included
- **[N]** No: discard all findings
- **[E]** Edit: let me revise before submitting
- **[Q]** Queue locally: save every finding to {localFallbackFolder}/, submit nothing

_You are the final filter. Reject any finding that doesn't reflect a real issue you observed._"

**HALT and wait for user input.**

#### Menu Handling:

- **IF Y or A:** Proceed to step 5
- **IF N:** Display "Findings discarded. Workflow complete." When `{result_envelope_line}` is bound (§0), display it verbatim after that, as the last line. STOP
- **IF E:** Let the user keep, modify or remove findings, and make each change in that finding's draft. A change to a finding's severity, workflow, step file, section, defect name or short description changes its fingerprints or its title, and one into or out of the workflow `health-check` changes its route: write its names file anew, run §3's fingerprint call again and, when `{fp}` changed, write the draft anew under the new `{fp}`; check each changed draft as §3 does. Then show the revised findings as above and ask again. When the edit leaves no finding, handle it as **IF N**.
- **IF Q:** Write every finding, whatever its severity, to the local queue (§5c) with the reason "The review gate queued these locally.", or the GATE's own reason in a headless run; one that §3 sent there keeps its reason, as §5 says. STOP after §5c

### 5. Route Each Finding by Severity

Route each finding the review gate approved:

- **\[Y]**, and a headless run that chose it: each finding whose severity is in `{liveSubmitSeverities}`, a `bug`, goes to the live-submit path (step 5a below), and each `friction` and `gap` finding to the local queue (step 5c below) with the reason "Friction and gap findings stay local unless you choose [A]." in an interactive run, and "Headless runs never submit friction or gap findings." in a headless one.
- **\[A]**: every finding goes to the live-submit path (step 5a below).
- Under either, a finding about the health check itself goes to the local queue with §4's reason, and one that §3 sent there keeps its reason: none of them is submitted.

### 5a. Live-Submit Path: Dedup and Create

For each finding routed to live-submit:

**1. Check the local seen-cache** at `{seenCachePath}`:

```
uv run {seenCacheHelper} lookup --fp "{fp}" --legacy-fp "{legacy_fp}" --repo "{healthCheckRepo}"
```

It prints `{"verdict", "record", "matched_on", "opening_line"}`. If the call fails or prints no JSON, continue as `unseen`: this check never halts a run. Act on `verdict`:

- `handled`, the only verdict that suppresses: skip the finding and log `"{fp}: already handled on {date}, issue {url}, skipping"`.
- `unseen` and `unrecognized`: submit it as a first sighting. When `matched_on` is `legacy_fp`, log `"{fp}: legacy record {legacy_fp} may be another defect, reporting"`.
- `regression`: file it under `{regression_title}` in place of `{title}` (§5a-ii, §5c), and add a `## Regression` section to the draft right above `## Finding`, holding the `opening_line` exactly as printed.
- `possible-regression`: add the same section, and keep `{title}`: the fix it links may be another defect's.

Every verdict but `handled` goes on to sub-step 2. If adding the `## Regression` section fails, log its error and write the finding to the local queue (§5c) with the failed-submission reason.

**2. Check GitHub CLI availability** with `gh auth status`. If it runs and fails (no `gh`, or not logged in), fall through to step 5c with the gh-unavailable reason.

**A refused `gh` call.** When the session refuses `gh auth status` or any later `gh` call of §5a, so that the command never ran, make no further `gh` call in this check: a refused call is no failure, so it gets no retry and no other call after it. Write this finding and every live-submit finding not yet submitted to the local queue (§5c), with the refused-gh reason. A finding already submitted stays submitted, and its record stays.

**3. Remote dedup search**: one deterministic call, and a second only when the first finds nothing:

```
gh search issues --repo {healthCheckRepo} --state open "{fp} in:title" --json number,url,title --limit 1
```

An issue it finds reports this defect. When it finds none, search once more, for the section fingerprint in titles and bodies:

```
gh search issues --repo {healthCheckRepo} --state open "{legacy_fp} in:title,body" --json number,url,title --limit 5
```

Each issue this second search finds is only a possible match: the user decides at 5a-i.

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
> It carries this section's fingerprint `{legacy_fp}`, which every `{severity}` finding in this section shares, so it may report another defect. Pick **\[R]** or **\[C]** only if it reports this one, naming it when more than one is listed, and **\[N]** if none does. Options:"

**Headless default: \[S].** Only the user decides a match: a headless run takes **\[S]** at an exact or a possible match, with the match or the possible-match reason.

Execute the chosen action:

- **R:** `gh api --hostname {healthCheckHost} -X POST repos/{healthCheckOwnerRepo}/issues/{N}/reactions -f content='+1'`
- **C:** Write the delta body, the Environment table plus one sentence on what differs from the original, with no session narrative, with the Write tool to `{localFallbackFolder}/bodies/{fp}-comment-{timestamp}.md`, check that file as §3 checks a draft, and show the user its text. Then run the same reaction call, then `gh issue comment --repo {healthCheckRepo} {N} --body-file "{localFallbackFolder}/bodies/{fp}-comment-{timestamp}.md"`. If the Write fails, make no call for this finding: log the error and write the finding to the local queue (§5c) with the failed-submission reason; a comment the check refused twice or could not check posts nothing either, and the finding goes there with the unchecked-draft reason.
- **N:** After a match found by `{fp}`, a new issue under that fingerprint would be closed as its duplicate: choose a more specific defect name that sets this defect apart, still in the source's words, write the names file anew, run §3's fingerprint call again and write and check the draft anew under the new `{fp}`, as §3 does, without a section the old verdict added, then run sub-steps 1 to 3 again for it. When the new `{fp}` is the old one, take **S** instead. After a possible match, go on to 5a-ii as is: that issue's `fp-*` label differs from `{fp}`.
- **S:** Record nothing, and write the finding to the local queue (§5c) with the reason "You skipped these at the dedup gate."; a headless run's **\[S]** takes the match or the possible-match reason instead (**Headless default** above).

If the **R** or **C** call exits non-zero, log its stderr message and make no further call for this finding: **C** posts no comment after a failed reaction, and a reaction it already added stays. Record nothing (run neither record call below) and write the finding to the local queue (§5c) with the failed-submission reason.

When every call of **R** or **C** succeeded, record the outcome under `{fp}`, also when the match was found by `{legacy_fp}`: `reacted` after **R** and `commented` after **C**, with the matched issue's `url` and today's date as YYYY-MM-DD:

```
uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" --date "{today}"
```

When sub-step 1 returned `regression`, run this one instead, since this open issue now tracks the recurrence:

```
uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" --date "{today}" --regression
```

Read what the call prints as §5b says; if it fails, log its stderr message and go on.

**5a-ii. If no matching open issue exists**, create a new issue from the finding's draft (§3).

**First, create the `{fp}` label**, which the create's `--label` needs. Run it on its own:

```
gh label create --repo {healthCheckRepo} "{fp}" \
  --color "ededed" \
  --description "Health-check fingerprint dedup key"
```

If it exits non-zero, that is no error: the label exists already, or you have no push access to `{healthCheckRepo}` and cannot create one. Go on to the create.

**Then create the issue:**
```
gh issue create \
  --repo {healthCheckRepo} \
  --title "{title}" \
  --label "health-check,workflow-improvement,{severity},{fp}" \
  --body-file "{draft_path}"
```

When sub-step 1 returned `regression`, put `{regression_title}` in that `--title` value in place of `{title}`. A `possible-regression` gets its `## Regression` section and no title marker. Keep the title's `[health-check][{severity}][{fp}] {workflow}: ` prefix exactly as the helper printed it: the dedup Action reads the severity and the fingerprint from it to label an issue filed without labels.

After the issue is created, record it under `{fp}` as §5b says.

If `gh issue create` exits non-zero, run it once more without its `--label` line, with the same title (`{regression_title}` after a `regression` verdict) and the same body file: a reporter without push access to `{healthCheckRepo}` can set no label, and the dedup Action labels the issue from its title. If the retry exits non-zero too, log its stderr message, record nothing, and write the finding to the local queue (§5c) with the failed-submission reason.

After creating all issues, display those that were created, `{N}` counting only them, unless none was (a create that failed is listed by §5c):

"**{N} issue(s) created on {healthCheckRepo}:**
{list each issue URL}"

**Closing line.** The step displays "Workflow complete." once, after everything else it displays but a bound `{result_envelope_line}` (§0). When any finding of this run goes to the local queue (§5c), display nothing more here: §5c ends its block with that line. Otherwise display "Workflow complete." now, after the block above, or alone when no issue was created. When `{result_envelope_line}` is bound (§0), display it verbatim after that line, as the last line.

### 5b. On success, update the seen-cache

After each successful `gh issue create`, on its first run or its retry without `--label` (§5a-ii), record the new issue under `{fp}`, with the URL `gh issue create` printed and today's date as YYYY-MM-DD:

```
uv run {seenCacheHelper} record --fp "{fp}" --action created --issue-url "{new_issue_url}" --date "{today}"
```

When sub-step 1 returned `regression`, run this one instead: the new issue tracks the recurrence, so it replaces the `resolved` record the fix left under `{fp}`.

```
uv run {seenCacheHelper} record --fp "{fp}" --action created --issue-url "{new_issue_url}" --date "{today}" --regression
```

It prints `{"written", "fp", "record", "set_aside"}`. `"written": false` is no error: the helper kept a `resolved` record, which only `--regression` replaces. If the call fails, log its stderr message and go on: a lost record costs at most a duplicate report, which the dedup Action closes. When `set_aside` is not null, after this call or §5a-i's, tell the user that `{seenCachePath}` did not parse, so it was renamed to that path and a new cache was started, and that they keep its records by fixing that file and copying its entries into `{seenCachePath}`.

**The `action` vocabulary is `created`, `reacted`, `commented`, `resolved`.** The first three are written by this workflow; `resolved` is recorded once the defect is fixed, with the helper's `record --action resolved`. Nothing else is recorded: not a queued finding, not **\[S]**, not a failed or refused call. A queued finding is not an issue, and a record for it would suppress the same defect when a later run approves it.

### 5c. Local-Queue Path (Every Finding That Stays Local)

Each finding here carries the reason its route gave it: **\[Q]** or a headless run (§4), the health check itself (§4), friction or gap under **\[Y]** (§5), a missing helper, no fingerprint, an unchecked draft, no repository or a refused call, which skips §4 before the gate (§3), gh unavailable or refused (§5a sub-step 2), **\[S]** (§5a-i), or a reaction, comment or new issue that failed to post (§5a-i, §5a-ii).

Write each such finding into `{localFallbackFolder}` with the helper, `{title}` being the finding's title, or its `{regression_title}` after a `regression` verdict whose `## Regression` section was added (§5a sub-step 1):

```
uv run {seenCacheHelper} queue --queue-dir "{localFallbackFolder}" --body-file "{draft_path}" --title "{title}" --repo "{healthCheckRepo}"
```

It copies the draft, unchanged and with no frontmatter, to `{localFallbackFolder}/hc-{workflow}-{YYYYMMDD-HHmmss}.md` (UTC) and prints `{"path", "commands"}`: the file it wrote and the three commands that submit it. A finding with the fingerprint `N/A` gets no queue call, and nor does any finding when `{healthCheckRepo}` is no repository (§3) or after a refused call (§3): list its draft (§3) in the queue file's place, or display the text of a finding that has no draft on disk, as when the call fails or prints no JSON (log its error then), followed, in place of commands, by "Submit it as <https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/#submitting-a-queued-finding> says." A block that lists no queue file ends with `{reason}` alone.

After writing the files, display one block per reason, each listing its own files, the first block alone when every finding has the same reason, then "Workflow complete." after the last block:

"**{N} finding(s) saved locally:**
{each path written, each followed by its three `commands`, exactly as printed, and, for a finding queued at a match (§5a-i), the URL of each issue it matched}

{reason} Run a finding's first two commands to submit it as an issue (the first fails, harmlessly, when its label exists), or open one at <https://{healthCheckHost}/{healthCheckOwnerRepo}/issues/new/choose>. Without push access to {healthCheckRepo}, run its third command alone instead: you can neither create a label nor set one, and the dedup Action labels the issue from its title."

`{reason}` is the sentence that says why the findings stayed local: the one its route quotes, or the one named here: "SKF's health-check helper is missing; re-install SKF to submit these." (the missing-helper reason), "SKF's health-check helper could not fingerprint these findings, so they carry the fingerprint N/A; compute it with its fingerprint call before submitting." (the could-not-fingerprint reason), "GitHub CLI is not available." (the gh-unavailable reason), "You declined one of the health check's calls; nothing more was posted." and "A call of the health check was refused in this session; allow its helper, its writes and its gh commands, as health_check_autosubmit's docs say, to submit headless." (the refused reason, interactive and headless), "health_check_repo in _bmad/skf/config.yaml is not a repository; fix it, then submit these." (the no-repository reason), "These drafts may name a folder of yours; check them before submitting." (the unchecked-draft reason), "You declined a gh call; nothing was posted." and "A gh call was refused in this session; allow the health check's gh commands, as health_check_autosubmit's docs say, to submit headless." (the refused-gh reason, interactive and headless), "These match an open issue with the same fingerprint; react or comment there, or file them anyway, after review." (the match reason), "These may match an open issue from the same section; review them before submitting." (the possible-match reason) or "Posting these to GitHub failed." (the failed-submission reason).

"Workflow complete."

When `{result_envelope_line}` is bound (§0), display it verbatim after that block, as the last line.
