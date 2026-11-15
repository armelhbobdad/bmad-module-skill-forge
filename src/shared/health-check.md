---
name: 'health-check'
description: 'Workflow self-improvement health check — captures real friction as GitHub issues'
# No nextStepFile — this is always the terminal step
healthCheckRepo: '{health_check_repo}'  # §0 resolves it: empty turns the check off, absent is armelhbobdad/bmad-module-skill-forge
healthCheckAutosubmit: '{health_check_autosubmit}'  # on only when exactly true (§4): a headless run then submits its bug findings
localFallbackFolder: '{forge_data_folder}/improvement-queue'  # forge workspace artifact — use forge_data_folder (single, unambiguous SKF var), NOT output_folder (a Core Config var that resolves differently across co-installed BMad modules)
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

Reflect on the workflow that just completed. If real friction, bugs, or gaps were encountered in the SKF workflow instructions, capture them as structured findings for the user to review and optionally submit as GitHub issues.

**Zero overhead for clean runs.** If nothing went wrong, say so and exit immediately.

## MANDATORY EXECUTION RULES:

### Universal Rules:
- Read the complete step file before taking any action
- Speak in `{communication_language}`

### Findings Rule:
Zero findings is the expected outcome of a good run. Report only a bug, friction or gap you hit in this session, each with the step file and section where it happened, and leave out anything you cannot tell apart from your own confusion: a finding you invent can become a real GitHub issue filed against the module.

---

## MANDATORY SEQUENCE

### 0. Announce Arrival

**Result envelope line.** A workflow may bind `{result_envelope_line}` before it loads this step, in headless mode only (Brief Skill also in an `[auto]` run), to the result envelope line its run printed through the shared emitter (its `SKF_<NAME>_RESULT_JSON: ...` line; skf-test-skill's report step binds its `SKF_TEST_RESULT_JSON` line). When it is bound and not empty, wherever this step stops (the off switch below, the clean-run stop in §2, the stop when no finding survives §3, **\[N]** at the review gate in §4, the closing line of §5a-ii, or the end of §5c) it displays that line verbatim as its very last line, after everything else it displays, with no code fence and nothing after it. In a standalone headless run, such as `claude -p`, which prints only the final message, that line is then the final message a pipeline reads. A workflow that binds nothing gets nothing extra.

**Off switch.** Before anything else, read the `health_check_repo` and `health_check_autosubmit` keys of `{project-root}/_bmad/skf/config.yaml` yourself: a workflow binds only its own config keys, so neither frontmatter value is bound for you. A missing `config.yaml` counts as both keys absent: the default repository, autosubmit off. Resolve `{healthCheckRepo}` from `health_check_repo`:

- The key is there with an empty value: `''`, `""`, nothing after its colon, only whitespace, or a YAML null (`~`, `null`, `Null` or `NULL`). The health check is off. Display the two lines below, then, when `{result_envelope_line}` is bound, that line verbatim, as the last line. STOP: announce nothing, and read no workflow context and reflect on nothing.

  "**Health Check: off.** `health_check_repo` is empty in `_bmad/skf/config.yaml`, so nothing was reviewed or sent.

  Workflow complete."

- The key is absent (a BMAD Method install writes none), or `{healthCheckRepo}` is still the unresolved `{health_check_repo}`: `{healthCheckRepo}` is the default, `armelhbobdad/bmad-module-skill-forge`.
- Otherwise, when the value is `OWNER/REPO` or `HOST/OWNER/REPO`, the shape the helper's `--repo` takes (letters, digits and `-` in the owner, `.` too in a host, `.` and `_` too in the repository, the host and the owner starting with a letter or a digit), `{healthCheckRepo}` is that value, the repository every issue of this step is filed on.
- Any other value (a URL, a value with a space, a quote or another shell character) is no repository. Display one line, "**Health Check:** `health_check_repo` is `{the value}` in `_bmad/skf/config.yaml`, which is not OWNER/REPO or HOST/OWNER/REPO, so no finding will be submitted.", and go on: the check reflects and drafts as usual, runs no `gh` call, and sends every finding to the local queue (§5c) with the reason "health_check_repo in _bmad/skf/config.yaml is not a repository; fix it, then submit these.", which replaces any reason its route would give but §4's for a finding about the health check itself.

Resolve `{healthCheckAutosubmit}` from `health_check_autosubmit`: it is on only when the key's value is exactly `true`; absent, unresolved or any other value is off.

**Display in `{communication_language}`:**

"**Running a quick self-improvement check on this workflow.** If nothing rough came up, I'll close out immediately."

**GATE [default: skip]**: if `{headless_mode}`, skip the display entirely, log: "headless: skipped health-check arrival announcement".

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

When `{result_envelope_line}` is bound (§0), display it verbatim after that, as the last line.

**STOP HERE. Do not proceed further. The workflow is done.**

### 3. Draft Each Finding (Only If Issues Exist)

Every finding, whatever its route, gets its fingerprints, its title and its issue body on disk before anyone reviews it: the review gate shows the drafts (§4), `gh` posts them (§5a-ii) and the local queue copies them (§5c), so **\[Q]** and a headless run queue the text the gate shows.

**Severity definitions:**
- **`bug`**: step instructions were wrong or contradictory
- **`friction`**: the step worked but was unclear, ambiguous, or caused unnecessary back-and-forth
- **`gap`**: a scenario arose that the workflow didn't account for at all

**A defect in this step.** A defect in this file's own instructions, or in the helper or a `gh` command it runs, that bites while this step runs is a finding about the health check itself: its workflow is `health-check` and its step file `shared/health-check.md`. It is never posted (§4). Take at most one per check: name, fingerprint and draft it as below, also when it bites after the review gate, and queue it (§5c) with the own-stage reason. Display any further one only as a one-line note, `Health check note: {what bit}, in shared/health-check.md "{section heading}".`, and draft nothing for it.

**Resolve the helper.** Resolve `{seenCacheHelper}` from `{seenCacheProbeOrder}`; first existing path wins. Its last entry, `shared/scripts/skf-health-check-seen.py`, resolves from the SKF module root, as every `shared/` path in this file does (the path convention above): the folder that holds the `shared/` folder this file was loaded from, which is where a plugin install, with neither `{project-root}/_bmad/skf/` nor `{project-root}/src/`, keeps it. The helper computes both fingerprints and the title, looks them up in the seen-cache (§5a sub-step 1), records each outcome there (§5a-i, §5b) and saves each finding that stays local to the queue (§5c), so neither fingerprint is hashed by hand and `{seenCachePath}` is never read or written by hand. If no candidate exists, give each finding the fingerprint `N/A`, write its draft by hand as **Write the draft** says, and send every finding that §4 does not discard to the local queue (§5c) with the missing-helper reason instead of submitting it: there is no fallback.

**A refused call.** A call the session refuses never ran (a permission prompt answered no, or a headless run with no rule that allows it), so a refused helper call (any `uv run` of `{seenCacheHelper}`) is no missing helper and a refused Write no failed one. After the session refuses a helper call or a Write of this step, make no further helper call, Write or `gh` call in this check, and send every finding not yet submitted to the local queue (§5c) with the refused reason, "You declined one of the health check's calls; nothing more was posted." in an interactive run, and "A call of the health check was refused in this session; allow its helper, its writes and its gh commands, as health_check_autosubmit's docs say, to submit headless." in a headless one. A refused `gh` call is §5a sub-step 2's.

**Name the step file, the section and the defect.** The step file is the `references/` file whose instruction bit, and `{workflow}` is the folder name of the workflow whose `references/` folder holds it, such as `skf-test-skill`, never `test-skill` or a display name: usually the workflow that just ran, and the other workflow for a step file loaded from its `references/` (Update Skill loads `skf-create-skill/references/extraction-patterns.md`, a file of `skf-create-skill`). The section is the heading of the innermost section of the step file that holds the instruction, copied exactly as the file writes it, numbering included. A bold run-in label (`**Foo.**`) is no heading: take the heading that encloses it. A defect in an instruction of the workflow's SKILL.md, of a script or of a `shared/references` file takes the step file that was running when it bit and the heading of that file's section that was running, or the file's H1 when none fits. The defect name names the defect itself, so two different defects in one section get two fingerprints while two reports of one defect that name the same thing get the same one. It is the thing the fix would change, in the step file's or the code's own words: a script by its file name, a function, a script subcommand, a field, a flag, a rule's term or a section's concept. Pick the most specific name the fix would edit. When the defect is a missing rule, there is no name to copy yet: name the case the rule should cover in two to four of the step file's own words, the noun the rule would be about, then what makes the case distinct. A wrong check in `floor_check` gives `floor-check`, a misread `--orphan-action` flag gives `orphan-action`, and a missing rule for a `const` holding a function, in a step file whose rule covers a `const` holding a component, gives `const-holding-function`. Never use a path, a line number, a severity, or words from this session's own story: whoever reports the same defect next must reach the same key from the source alone. Never use the section's own subject alone either: every defect in the section shares it.

**Give it a short description**, one line naming the defect for its issue title, with no backtick, `$`, double quote, backslash or `!`: the title goes on the command line.

Write the two names and the description with the Write tool to `{localFallbackFolder}/bodies/names-{timestamp}-{i}.json`, `{timestamp}` being the time of the write as YYYYMMDD-HHmmss and `{i}` the finding's number, as the JSON object `{"section_heading": "<the heading>", "defect_name": "<the name>", "short_description": "<the description>"}` with each value JSON-escaped, so no quote in a name meets the shell. If the Write fails, or the shell says it cannot open that file, make no fingerprint call for this finding (a call that cannot read its names file prints no JSON, which does not mean the helper is missing): log the error, naming the finding, give the finding the fingerprint `N/A` and send it to the local queue (§5c) with the could-not-fingerprint reason. Otherwise run the helper once per finding, with that finding's severity, workflow and step file (its name, or any path to it):

```
uv run {seenCacheHelper} fingerprint --severity "{severity}" --workflow "{workflow}" --step-file "{step_file}" --stdin < "{localFallbackFolder}/bodies/names-{timestamp}-{i}.json"
```

It prints `{"fp", "legacy_fp", "tuple", "step_file", "section_slug", "defect_key", "title", "regression_title", "body_header"}`. `{fp}` is `fp-` and the first 7 hex characters of `sha1("{severity}|{workflow}|{step_file}|{section-slug}|{defect-key}")`, and `{legacy_fp}` the same hash without `|{defect-key}`. `tuple` is that sha1 input. From here on, `{step_file}`, `{section-slug}` and `{defect-key}` are the call's `step_file`, `section_slug` and `defect_key`: the helper writes each in one form, so one finding gets one fingerprint from a checkout, a CLI install or a plugin. `{title}` is the issue title, `[health-check][{severity}][{fp}] {workflow}: {short description}`, and `{regression_title}` the same with `REGRESSION: ` before the description: use them exactly as printed, wherever this finding's title appears. When what it prints has no `title`, the names file held no description: add it there and run the call once more.

- `step_file` is `src/{workflow}/references/{file}.md`, whatever path the call was given, and `src/shared/health-check.md` for the workflow `health-check`.
- The section slug is the heading with its leading `#`s and its numbering token (`5a.`, `5a-ii.`) dropped, lower-cased, each run of characters other than ASCII letters and digits turned into one hyphen and the hyphens at its ends trimmed: `### 5a. Live-Submit Path: Dedup and Create` gives `live-submit-path-dedup-and-create`. A line number never enters it. A heading copied in another letter case or with other punctuation gives the same slug, so the helper takes it as that heading.
- The defect key is one to four lower-case ASCII words joined by hyphens that name the thing the fix would change. The helper drops the backticks or quotes around the name, keeps its last path component, drops a `:N`, `:N-M` or `:N:M` line suffix, a file extension and then its leading dashes and underscores, splits it at spaces, underscores, hyphens, dots and each lower-case letter followed by an upper-case one, drops every character of each word that is not an ASCII letter or digit, lower-cases each word and joins them with hyphens (`scripts/gate_eval.py:42:7` gives `gate-eval`, `composeStories` gives `compose-stories`, `reader's own code` gives `readers-own-code`); a name of more than four words keeps its last four.

`legacy_fp` is the section fingerprint, the fingerprint without the key, which every defect of one severity in one section shares. Issues and seen-cache records made by an SKF version without the key carry it as their fingerprint, and every issue this step files records it in its body (the `body_header`), so a match on it is only ever a possible match (§5a sub-steps 1 and 3).

A value that breaks its rule makes the call exit 2 and print one `{"status": "error", "message": ...}` line on stderr that names the rule: a severity other than `bug`, `friction` or `gap`, a workflow that is not one of the 15 workflow folders or `health-check`, a step file that is not a file of that workflow's `references/` folder (or is its `health-check.md` relay; for `health-check`, anything but `shared/health-check.md`), a heading that is not one of that step file's own, a name that yields no word, a description that holds a backtick, `$`, double quote, backslash, `!` or line break or makes the regression title longer than 256 characters, or a names file that is not that JSON object. When it names the severity, the workflow, the step file, the name, the description or the names file, fix that value and run the call once more; when it refuses the heading, take the heading that encloses that one (the file's H1 at the top) and run the call once more. Never loop: when that second call is refused too, log its message, naming the finding, give the finding the fingerprint `N/A` and send it to the local queue (§5c) with the could-not-fingerprint reason instead of submitting it. A call that prints no JSON on stdout and no such line on stderr did not run the helper (uv or Python could not start it, and uv's own errors exit 2 as well): treat it as a missing helper, so the finding gets the fingerprint `N/A` and goes to the local queue (§5c) with the missing-helper reason. Two findings that get one `{fp}` are one defect: merge them into one finding before drafting.

**Write the draft.** Write each finding's issue body (the format below) with the Write tool to a file of its own, `{localFallbackFolder}/bodies/{fp}-{timestamp}.md`, `{timestamp}` being the time of the write as YYYYMMDD-HHmmss, opening with the call's `body_header` exactly as printed. From here on `{draft_path}` is the path of the draft this step wrote for the finding. SKF has no run folder at this step, so every draft lives in `bodies/`. Every route uses that file as it stands: the review gate shows it (§4), `gh` posts it with `--body-file` (§5a-ii) and the queue copies it (§5c). After the gate it changes only by a regression's `## Regression` section (§5a sub-step 1) or an **\[N]** re-key at the dedup gate (§5a-i). The body quotes paths, evidence and its `Section fingerprint:` line in backticks: on the command line, inside double quotes, the shell would run each backticked span or `$(...)` as a command and put its output in its place, and a double quote in it would end the argument. So a body never goes on the command line, and the file is never written through the shell (`echo`, `printf` or a heredoc), which can expand it the same way. If the Write fails, log the error, naming the finding, and drop the finding: there is no text to show, post or queue. When no finding survives this step, display "**Health Check:** no finding could be drafted, so nothing was reviewed or sent." and then "Workflow complete.", then, when `{result_envelope_line}` is bound, that line verbatim, as the last line, and STOP. The file stays after the run, in `bodies/` apart from the findings the queue holds, as the record of what was sent or tried.

A finding with the fingerprint `N/A` has no `body_header`: write its header by hand in the same form, with the workflow, the step file as `src/{workflow}/references/{file}.md` (`src/shared/health-check.md` for the health check itself), the section's heading as the step file writes it, the severity, `N/A` as the Fingerprint and in the `Section fingerprint:` line, and the defect name, each in backticks. Name its draft `{localFallbackFolder}/bodies/hc-{workflow}-{timestamp}-{i}-draft.md`, `{i}` being the finding's number, and its title `[health-check][{severity}][N/A] {workflow}: {short description}`.

**Writing rules (non-negotiable):**

- **One issue per finding.** If you observed two independent problems, submit two issues.
- **Respect the length budgets.** Finding, Expected, Actual, Impact are each ONE sentence. Evidence is 2-5 bullets, not prose. Suggested Fix is 1-3 sentences with ONE recommendation: multiple options go in the `Alternatives considered` collapsible or (better) not at all.
- **Quote, don't paraphrase.** In Evidence, cite the exact `file:line` and put the quoted text in quotes. Link the convention to the instruction that caused it.
- **Name nothing of the user's.** The title, every section of the body and a **C** comment describe SKF's instruction, never the user's work: they name no project, library, skill, file or path of the user's and no secret, and Evidence quotes only SKF's own files (its step files, SKILL.md files, shared files and scripts), never the user's project code, the source a skill was built from or a brief's or a skill's content: an issue on the default repository is public.
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
<!-- ONE sentence. What is the problem? Do not explain why yet. -->
{e.g. Step 5 forbids writes to the skills output folder but does not name a staging directory.}

## Expected
<!-- ONE sentence. What did the step instruct or imply should happen? -->
{e.g. The step should name the staging directory between assembly and final write.}

## Actual
<!-- ONE sentence. What did you observe instead? -->
{e.g. No staging path was named, so the step wrote its artifacts straight to the skill's final folder and step 7 had to move them.}

## Evidence
<!-- Bulleted `file:line` citations of SKF's own files. 2-5 bullets. No narrative prose. -->
- `path/to/file.md:17`: "quoted text from the file"
- `path/to/other.md:62`: brief note on what it shows

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
| Run Mode | {interactive or headless} |
| SKF Version | {the `version` the helper prints, below, else N/A} |
```

In the header, `{fp}` is the deterministic dedup key, `sha1(severity|workflow|step_file|section-slug|defect-key)[:7]` over the fields as the header writes them, also applied as a label so maintainers can filter all variants server-side. The `Section fingerprint:` line carries `{legacy_fp}`, the same hash without the defect key, shared by every defect of this severity in this section: body text only, never a label, since the dedup Action reads it to flag possible duplicates. Run Mode is `headless` when `{headless_mode}` is true, else `interactive`.

**SKF Version comes from the helper**, which reads the version of the SKF it belongs to, whatever the install (a CLI install's `_bmad/skf/VERSION`, a checkout's or a plugin's `package.json`), never from `{project-root}`:

```
uv run {seenCacheHelper} version
```

It prints `{"version": ..., "source": ...}`. Write `version` into the Environment table; write `N/A` when it is null, when the call fails or prints no JSON, or when no helper exists.

### 4. User Review Gate

**A finding about the health check itself.** A finding whose workflow is `health-check` (§3) is never posted. Every route that submits or queues it (**\[Y]**, **\[A]**, **\[Q]** and a headless run) writes it to the local queue (§5c) with the reason "Found in the health check's own instructions; review it before submitting.", which replaces any reason its route would give; **\[N]** discards it with the rest. Filing it would have the run's last step post a report about itself, and a defect in that filing would call for another.

**GATE [default: Q]**: if `{headless_mode}` is true, skip the question below and choose by `{healthCheckAutosubmit}`, which is on only when it is exactly `true` (`health_check_autosubmit: true`, added to `_bmad/skf/config.yaml` by hand; absent, unresolved or any other value is off): while it is off, choose **[Q]**, with the reason "Headless runs queue every finding while health_check_autosubmit is off.", and log: "headless: queued {N} finding(s) locally"; when it is on, choose **[Y]**, which submits the bug findings, still deduped, and queues the friction and gap findings with the reason "Headless runs never submit friction or gap findings.", and log: "headless: autosubmit on, submitting bug findings only". Then go to Menu Handling. Nobody approves a public post in a headless run, so it posts nothing but a bug finding's new issue, and takes **\[S]** at any matching issue (§5a-i).

**If interactive:** show every finding: for each one, its title (§3), the path of its draft and the draft's full text. Say that when the seen-cache check finds the defect was fixed before, a `## Regression` section naming that fix is added to the draft above `## Finding`, and a confirmed regression is filed under its regression title, `REGRESSION: ` before its short description (§5a sub-step 1). Say too that a finding about the health check itself is queued, never posted, whatever the user chooses but **\[N]**. When no finding can be submitted, because each one is about the health check itself or has the fingerprint `N/A` (§3), or `{healthCheckRepo}` is no repository (§0), ask instead "**Queue these findings locally?**" with **\[Q]**, **\[N]** and **\[E]** only.

Then ask, saying "public issues" for "issues" when `{healthCheckRepo}` is the default, `armelhbobdad/bmad-module-skill-forge` in any letter case, and for any other repository adding "(public if that repository is public)" after its name:

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
- **IF E:** Let the user keep, modify or remove findings, and make each change in that finding's draft. A change to a finding's severity, workflow, step file, section, defect name or short description changes its fingerprints or its title, and one into or out of the workflow `health-check` changes its route: write its names file anew, run §3's fingerprint call again and, when `{fp}` changed, write the draft anew under the new `{fp}`. Then show the revised findings as above and ask again. When the edit leaves no finding, handle it as **IF N**.
- **IF Q:** Write every finding, whatever its severity, to the local queue (§5c) with the reason "The review gate queued these locally.", or the GATE's own reason in a headless run. STOP after §5c

### 5. Route Each Finding by Severity

Route each finding the review gate approved:

- **\[Y]**, and a headless run that chose it: each finding whose severity is in `{liveSubmitSeverities}`, a `bug`, goes to the live-submit path (step 5a below): high signal, priority for maintainers. Each `friction` and `gap` finding, the most subjective kinds and the ones that draw the most near-duplicates, goes to the local queue (step 5c below) with the reason "Friction and gap findings stay local unless you choose [A]." in an interactive run, and "Headless runs never submit friction or gap findings." in a headless one.
- **\[A]**: every finding goes to the live-submit path (step 5a below).
- Under either, a finding about the health check itself goes to the local queue with §4's reason, every other finding with §0's reason when `{healthCheckRepo}` is no repository, and a finding with the fingerprint `N/A` (§3) with the missing-helper or the could-not-fingerprint reason: none of them is submitted.

### 5a. Live-Submit Path: Dedup and Create

For each finding routed to live-submit:

**1. Check the local seen-cache** at `{seenCachePath}`:

```
uv run {seenCacheHelper} lookup --fp "{fp}" --legacy-fp "{legacy_fp}" --repo "{healthCheckRepo}"
```

It prints `{"verdict": ..., "record": ..., "matched_on": ..., "opening_line": ...}`: the verdict, the record it came from, whether that record sits under `{fp}` or `{legacy_fp}` (`record` and `matched_on` are null when there is none), and the line a regression's issue body carries (null for any other verdict). The helper reads the file itself, and a missing, empty or corrupt cache is an empty one. The cache serves every project on the machine, so with `--repo` a record of an issue on another repository than `{healthCheckRepo}` counts as no record: it neither suppresses this finding nor gives its body a line linking that issue, and `gh` is never asked about it. If the call fails or prints no JSON, continue as `unseen`: this check never halts a run.

**Presence in the cache is not the verdict.** A fingerprint whose defect was already fixed must NOT suppress: a fresh sighting of a fixed defect is a *regression*, and it is the single most valuable report this loop can produce. The helper looks up `{fp}`, and only when the cache has no record for it, `{legacy_fp}`, then works its branches on the record found. For a record with the action `created`, `reacted` or `commented` and an issue URL, it asks the issue itself through `gh issue view`, stopped after 10 seconds: the cache is machine-local and records only what *this* user did, while the issue's state is shared, so it is the better authority. Act on the `verdict` it prints:

- `unseen`: no record under either fingerprint (a record of an issue on another repository counts as none), or a record found only under `{legacy_fp}` (`matched_on` is `legacy_fp`) that would have suppressed. That record was written by an SKF version without the defect key, and every defect of this severity in this section shares its fingerprint, so it may be another defect's: log `"{fp}: legacy record {legacy_fp} may be another defect, reporting"`, and sub-step 3 still offers its issue while that issue is open. Go to sub-step 2.
- `handled`: a record under `{fp}` whose issue is open, was closed as not planned (how the dedup Action closes a duplicate and a maintainer closes a wontfix, neither of them a fix) or could not be checked (offline, no `gh`, the time limit, a deleted issue), or one with no issue URL. Skip the finding, as the next paragraph says.
- `regression`: a record under `{fp}` marked `resolved` (with the helper's `record --action resolved`) once the defect was fixed, or whose issue was closed as completed (or whose pull request was merged). Go to sub-step 2 and apply the regression treatment below.
- `possible-regression`: the same, found only under `{legacy_fp}`, so what was fixed may be another defect in this section. Go to sub-step 2 and apply the possible-regression treatment below.
- `unrecognized`: a record with no `action` or one this file does not write, hand-edited or written by a newer version of this file, so it cannot be confirmed handled. Go to sub-step 2 as an ordinary submission.

**`handled` is the only verdict that suppresses.** Skip submission silently and log: `"fp-{hash}: already handled on {date}, issue {url}, skipping"`. Every other verdict proceeds to sub-step 2.

**Why anything uncertain reports instead of suppressing.** A duplicate report is self-healing: the dedup Action closes it and moves the upvote to the canonical issue. A silenced regression is caught by nothing at all. When the verdict is in doubt, report.

**Regression treatment** (verdicts `regression` only). Carry the prior record forward so the recurrence can never be filed as a first sighting:

- File the finding under `{regression_title}` (§3), the title with `REGRESSION: ` before its short description, in place of `{title}`: the create (§5a-ii) and the queue (§5c) take it.
- Add a `## Regression` section to the draft immediately above `## Finding`, containing one line: the `opening_line` sub-step 1 printed, exactly as printed. It links the prior issue and says how the fix is known: `Regression of {issue_url} (resolved {date}).` after a `resolved` record, whose date is the fix's, or `Regression of {issue_url}, closed as completed since its report on {date}.` after an issue closed as completed, whose record dates only the report. The `{fp}` label still ties the two together server-side.
- Leave `## Finding` and the other one-sentence sections exactly as drafted. The backlink lives in its own section precisely so those budgets are untouched.

**Possible regression** (verdict `possible-regression` only). The resolved record was found under `{legacy_fp}`, so what was fixed may be another defect in this section. Add the same `## Regression` section, with the `opening_line` sub-step 1 printed, exactly as printed, which says so: it ends `: that report's fingerprint has no defect key, so it may be another defect in this section.`, or reads `Possibly a regression of a previously resolved local finding in this section (resolved {date}).` when the prior record has no issue URL. Leave the title unmarked, `{title}`, since this record cannot prove a recurrence. The two reports carry different `fp-*` labels, so this line is their only link.

If adding the `## Regression` section to the draft fails, log its error and write the finding to the local queue (§5c) with the failed-submission reason.

**What this does and does not catch.** The fingerprint is `sha1` over the section slug and the defect key, so a fix that renames or relocates the section it touches, or renames the thing the key names, changes the fingerprint. So does a report that names the same defect by another thing than an earlier report did: independent reports of one defect often pick different keys. Such a report arrives as `unseen` and is reported as a first sighting, which is safe but unlinked here; once it is filed, the dedup Action flags it (§5a-ii). These branches catch the regressions that recur under the same heading in the same step file, under the same key, which is the case where the old behaviour was silent.

**2. Check GitHub CLI availability** with `gh auth status`. If it runs and fails (no `gh`, or not logged in), fall through to step 5c (local fallback) with the gh-unavailable reason.

**A refused `gh` call.** When the session refuses `gh auth status` or any later `gh` call of §5a, so that the command never ran (a permission prompt answered no, or a headless run with no rule that allows it), make no further `gh` call in this check: a refused call is no failure, so it gets no retry and no other call after it. Write this finding and every live-submit finding not yet submitted to the local queue (§5c), with the reason "You declined a gh call; nothing was posted." in an interactive run, and "A gh call was refused in this session; allow the health check's gh commands, as health_check_autosubmit's docs say, to submit headless." in a headless one. A finding already submitted stays submitted, and its record stays.

**3. Remote dedup search**: one deterministic call, and a second only when the first finds nothing:

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

**Headless default: \[S].** Only the user decides a match. A headless run, which reaches this choice only with `{healthCheckAutosubmit}` on (§4), takes **\[S]** at an exact or a possible match, so the finding goes to the local queue (§5c) with the match reason after an exact match and the possible-match reason after a possible one, and nothing is posted on a guess.

Execute the chosen action:

- **R:** `gh api -X POST repos/{healthCheckRepo}/issues/{N}/reactions -f content='+1'`
- **C:** Write the delta body, the Environment table plus ONE sentence describing what's different from the original and no session narrative, with the Write tool to `{localFallbackFolder}/bodies/{fp}-comment-{timestamp}.md`, as **Write the draft** in §3 writes a draft, and show the user its text. Then run the same reaction call, then `gh issue comment --repo {healthCheckRepo} {N} --body-file "{localFallbackFolder}/bodies/{fp}-comment-{timestamp}.md"`. If the Write fails, make no call for this finding: log the error and write the finding to the local queue (§5c) with the failed-submission reason.
- **N:** After a match found by `{fp}`: the open issue carries this same fingerprint, so a new issue under it would be closed as its duplicate. Choose a more specific defect key that names what sets this defect apart (the more specific name the fix edits, or the case it covers, still in the source's words), write the names file anew with the new name, run §3's fingerprint call again on it and write the draft anew under the new `{fp}`, without a section the old verdict added, then run sub-steps 1 to 3 again for the new fingerprints and act on what they return as for any finding. When the new `{fp}` is the old one (the new name gives the same key), take **S** instead. After a possible match, proceed to step 5a-ii as is: that issue's `fp-*` label differs from `{fp}`.
- **S:** Record nothing, and write the finding to the local queue (§5c) with the reason "You skipped these at the dedup gate."; a headless run's **\[S]** takes the match or the possible-match reason instead (**Headless default** above).

The **R** and **C** calls name `{healthCheckRepo}`, as the step's other issue calls do: without it, `gh` reacts or comments on the repository of the folder the workflow ran in, usually the user's own project. If one of them exits non-zero, log its stderr message and make no further call for this finding: **C** posts no comment after a failed reaction, and a reaction it already added stays. Record nothing (run neither record call below) and write the finding to the local queue (§5c) with the failed-submission reason. When **C** fails, its comment file stays in `{localFallbackFolder}/bodies/`, its name starting with the finding's fingerprint.

When every call of **R** or **C** succeeded, record the outcome under `{fp}`, also when the match was found by `{legacy_fp}`: `reacted` after **R** and `commented` after **C**, with the matched issue's `url` and today's date as YYYY-MM-DD:

```
uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" --date "{today}"
```

When sub-step 1 returned `regression`, run this one instead: **R** or **C** says this open issue reports the defect, so it now tracks the recurrence and replaces the `resolved` record the fix left under `{fp}`.

```
uv run {seenCacheHelper} record --fp "{fp}" --action {reacted|commented} --issue-url "{url}" --date "{today}" --regression
```

**S** records nothing, and **N** records its new issue in §5b. Read what the call prints as §5b says; if it fails, log its stderr message and go on.

**5a-ii. If no matching open issue exists**, create a new issue from the finding's draft (§3).

**First, create the `{fp}` label**, which the create's `--label` needs: it is per-fingerprint, so the first reporter of a defect creates a new one, and `gh issue create` fails on a label that does not exist. Run it on its own:

```
gh label create --repo {healthCheckRepo} "{fp}" \
  --color "ededed" \
  --description "Health-check fingerprint dedup key"
```

If it exits non-zero, that is no error: the label exists already (a second reporter of a defect whose earlier issue was closed, or a parallel submission), or you have no push access to `{healthCheckRepo}` and cannot create one. Go on to the create. The other labels in the command below (`health-check`, `workflow-improvement`, `bug`/`friction`/`gap`) are pre-created repo labels.

**Then create the issue:**
```
gh issue create \
  --repo {healthCheckRepo} \
  --title "{title}" \
  --label "health-check,workflow-improvement,{severity},{fp}" \
  --body-file "{draft_path}"
```

The body file is the finding's draft, `{draft_path}` (§3), and `{title}` the title §3's call printed. When sub-step 1 returned `regression`, put `{regression_title}` in that `--title` value in place of `{title}`, and the draft holds the `## Regression` section. The command above is the literal one you run, so the marker has to be in it: an instruction that the title should say REGRESSION loses to a copied command that does not. A `possible-regression` gets its `## Regression` section and no title marker.

The fingerprint `{fp}` appears in both title (human-readable) and label (server-side filterable). Maintainers can query all reports for a defect via the `fp-*` label without relying on title text. Keep the title's `[health-check][{severity}][{fp}] {workflow}: ` prefix exactly as the helper printed it: the dedup Action reads the severity and the fingerprint from it to label an issue filed without labels.

The dedup Action reads the body's `Section fingerprint:` line too. When the new issue matches no open issue's fingerprint but another open health-check issue records the same section fingerprint under a different defect key, or was filed without a key and carries it as its label, the Action comments with a link to each such issue and adds the `possible-duplicate` label. It closes nothing on that match: two reports of one defect can name it by different keys, and every defect of one severity in one section shares the section fingerprint, so a maintainer decides.

After the issue is created, record it under `{fp}` as §5b says, so this user does not re-report it while that issue stays open.

If `gh issue create` exits non-zero, run it once more without its `--label` line, with the same title (`{regression_title}` after a `regression` verdict) and the same body file: a reporter without push access to `{healthCheckRepo}` can set no label, and the dedup Action labels the issue from its title. A create that succeeded on that retry is recorded as §5b says, as one that succeeded at once is. If the retry exits non-zero too, log its stderr message and record nothing: §5b runs only after a create that succeeded, so after a `regression` verdict the `resolved` record stays. Write the finding to the local queue (§5c) with the failed-submission reason, as a failed reaction or comment is: its queue file holds its draft, unchanged, so what failed to post is what waits to be submitted.

After creating all issues, display those that were created, `{N}` counting only them, unless none was (a create that failed is listed by §5c):

"**{N} issue(s) created on {healthCheckRepo}:**
{list each issue URL}"

**Closing line.** The step displays "Workflow complete." once, after everything else it displays but a bound `{result_envelope_line}` (§0). When any finding of this run goes to the local queue (§5c), display nothing more here: §5c writes its files, then ends its block with that line. Otherwise display "Workflow complete." now, after the block above, or alone when no issue was created because every finding was a reaction or a comment that posted (§5a-i) or one the seen-cache found handled (§5a sub-step 1). When `{result_envelope_line}` is bound (§0), display it verbatim after that line, as the last line.

### 5b. On success, update the seen-cache

After each successful `gh issue create`, on its first run or its retry without `--label` (§5a-ii), record the new issue under `{fp}`, with the URL `gh issue create` printed and today's date as YYYY-MM-DD:

```
uv run {seenCacheHelper} record --fp "{fp}" --action created --issue-url "{new_issue_url}" --date "{today}"
```

This file is global across the user's machine, not per-project, so the same defect is not re-reported across different repos the user works in while its issue stays open.

When sub-step 1 returned `regression`, run this one instead: the new issue tracks the recurrence, so it replaces the `resolved` record the fix left under `{fp}`.

```
uv run {seenCacheHelper} record --fp "{fp}" --action created --issue-url "{new_issue_url}" --date "{today}" --regression
```

It prints `{"written": ..., "fp": ..., "record": ..., "set_aside": ...}`, `record` being what the cache now holds under `{fp}`: `{"issue_url": ..., "action": "created", "date": "YYYY-MM-DD"}`. If the call fails, log its stderr message and go on: a lost record costs at most a duplicate report, which the dedup Action closes. When `set_aside` is not null, after this call or §5a-i's, tell the user that `{seenCachePath}` did not parse, so it was renamed to that path and a new cache was started, and that they keep its records by fixing that file and copying its entries into `{seenCachePath}`.

**What the helper guarantees.** It merges, never replaces: it sets the `{fp}` key alone and keeps every other fingerprint the user has recorded. It writes under `{fp}` only: a record under `{legacy_fp}` stays exactly as it is, whatever its action, since it may be another defect's. It never downgrades a `resolved` record: without `--regression` it leaves one alone and prints `"written": false`, so a fixed defect's suppression never comes back without a new open issue to justify it. It holds `{seenCachePath}.lock` while it reads and writes, so parallel SKF sessions keep each other's records, and it renames a cache that does not parse to `{seenCachePath}.corrupt-<UTC time>` (its `set_aside`) instead of discarding the records in it.

**The `action` vocabulary is `created`, `reacted`, `commented`, `resolved`.** The first three are written by this workflow. `resolved` is recorded once the defect is fixed, with the helper's `record --action resolved` and the fixing issue's or pull request's URL (or an empty one), and it is the only one that does not suppress; it replaces any record under its fingerprint. See the health-check section of `CONTRIBUTING.md` for when to record it. Nothing else is recorded: not a queued finding, not **\[S]**, not a failed or refused call. A queued finding is not an issue, and a record for it would suppress the same defect when a later run approves it.

### 5c. Local-Queue Path (Every Finding That Stays Local)

Each finding here carries the reason its route gave it: the review gate's **\[Q]** (§4), a headless run (§4), a finding about the health check itself (§4), a friction or gap finding under **\[Y]** (§5), SKF's health-check helper missing or unable to fingerprint a finding (§3), gh unavailable or a refused `gh` call (§5a sub-step 2), **\[S]** at the dedup gate, the user's or a headless run's (§5a-i), or a reaction, comment or new issue that failed to post (§5a-i, §5a-ii).

Write each such finding into `{localFallbackFolder}` with the helper, `{title}` being the finding's title, or its `{regression_title}` after a `regression` verdict whose `## Regression` section was added (§5a sub-step 1):

```
uv run {seenCacheHelper} queue --queue-dir "{localFallbackFolder}" --body-file "{draft_path}" --title "{title}" --repo "{healthCheckRepo}"
```

It copies the draft, unchanged and with no frontmatter, to `{localFallbackFolder}/hc-{workflow}-{YYYYMMDD-HHmmss}.md`, named by the UTC time of the copy, with `-2`, `-3` and so on before `.md` when that name is taken, so no file is overwritten. It prints `{"path", "commands"}`: the file it wrote and the three commands that submit it, the label create, the create and the create without labels, each argument quoted for a POSIX shell and `--repo` right after each subcommand. A finding with the fingerprint `N/A` gets no queue call (its draft has no `body_header` the helper can read), and nor does any finding when `{healthCheckRepo}` is no repository (§0) or after a refused call (§3): list its draft (§3) in the queue file's place, or display the text of a finding that has no draft on disk, as when the call fails or prints no JSON (log its error then), followed, in place of commands, by "Submit it as <https://armelhbobdad.github.io/bmad-module-skill-forge/workflows/#submitting-a-queued-finding> says."

After writing the files, display one block per reason, each listing its own files, the first block alone when every finding has the same reason, then "Workflow complete." after the last block:

"**{N} finding(s) saved locally:**
{each path written, each followed by its three `commands`, exactly as printed, and, for a finding queued at a match (§5a-i), the URL of each issue it matched}

{reason} Run a finding's first two commands to submit it as an issue (the first fails, harmlessly, when its label exists), or open one at <https://github.com/{healthCheckRepo}/issues/new/choose>. Without push access to {healthCheckRepo}, run its third command alone instead: you can neither create a label nor set one, and the dedup Action labels the issue from its title."

`{reason}` is the sentence that says why the findings stayed local: "The review gate queued these locally.", "Headless runs queue every finding while health_check_autosubmit is off.", "Headless runs never submit friction or gap findings.", "Found in the health check's own instructions; review it before submitting." (the own-stage reason), "Friction and gap findings stay local unless you choose [A].", "SKF's health-check helper is missing; re-install SKF to submit these." (the missing-helper reason), "SKF's health-check helper could not fingerprint these findings, so they carry the fingerprint N/A; compute it with its fingerprint call before submitting." (the could-not-fingerprint reason), "GitHub CLI is not available." (the gh-unavailable reason), "You declined a gh call; nothing was posted.", "You declined one of the health check's calls; nothing more was posted.", "A call of the health check was refused in this session; allow its helper, its writes and its gh commands, as health_check_autosubmit's docs say, to submit headless.", "health_check_repo in _bmad/skf/config.yaml is not a repository; fix it, then submit these.", "A gh call was refused in this session; allow the health check's gh commands, as health_check_autosubmit's docs say, to submit headless.", "You skipped these at the dedup gate.", "These match an open issue with the same fingerprint; react or comment there, or file them anyway, after review." (the match reason), "These may match an open issue from the same section; review them before submitting." (the possible-match reason) or "Posting these to GitHub failed." (the failed-submission reason).

"Workflow complete."

When `{result_envelope_line}` is bound (§0), display it verbatim after that block, as the last line.
