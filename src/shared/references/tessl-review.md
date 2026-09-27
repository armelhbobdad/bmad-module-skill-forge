# Tessl Review

Tessl Review scores a skill on Tessl's servers. It runs deterministic validation checks and two AI judges, one for the frontmatter `description` (specificity, completeness, trigger-term quality, distinctiveness) and one for the body and the files beside it (conciseness, actionability, workflow clarity, progressive disclosure), and weighs them into one review score from 0 to 100, with suggestions. It reads the whole skill folder, so a skill whose Tier 2 sections moved to `references/` is judged with them.

create-skill (step 6 §6b) and test-skill (step 4b §3) run it through `skf-tessl-review.py`. No step file runs tessl itself, and neither workflow halts, asks the user anything or changes a file because of a review.

## When It Runs

The helper checks these conditions in order and stops at the first one that fails:

1. **Opt-in.** `tessl_review_workspace` in `{sidecar_path}/preferences.yaml` names one of the user's Tessl workspaces. A missing key, `~`, `false` or an empty value means off, the default in interactive and headless runs alike. Setting the key is the user's consent to upload the files listed below to that workspace.
2. **Installed.** `tessl` is on `PATH`, or its npm launcher is already in the npx cache. SKF never installs tessl.
3. **Signed in.** `tessl whoami` succeeds: the user ran `tessl login`, or `TESSL_TOKEN` is set for an unattended run.

The helper's `submit` then sends the copy as `tessl review run <copy> --workspace <tessl_review_workspace> --no-wait --json` and removes the copy once tessl answers with the review's run id, and its `collect` reads the review with `tessl review view <run id> --json`, the only tessl command it runs. A check that fails without an answer SKF can read, or does not answer in time, is tried again, since Tessl may still finish the review. Every tessl call runs with a temporary folder as its working directory, so tessl never reads or writes the user's project.

## What Is Uploaded

Only the files an agent loads from the skill: `SKILL.md` and the `references/`, `scripts/` and `assets/` folders, copied without links into a temporary folder named after the skill. `metadata.json`, `context-snippet.md` and the workspace artifacts create-skill stages beside them (`provenance-map.json`, `evidence-report.md`) stay on the machine. Tessl keeps each review in the workspace's review history.

create-skill reviews the staged skill, which holds no `scripts/` or `assets/` until step 7 copies them, so for a skill with scripts or assets its validation findings may name those paths as missing. test-skill reviews the finished package.

## Cost and Time

Each fresh review spends credits from the Tessl account's plan, and each workflow run with the review on can spend one. Re-reviewing a skill folder Tessl has already reviewed can return Tessl's cached result without spending credits. A review takes Tessl about two minutes, and no helper call waits for all of it, so every call ends within two minutes, inside a shell tool's default time limit: `submit` returns as soon as Tessl has accepted the review, and each `collect` checks it for up to 90 seconds, then returns `pending` again or the result. The calling step collects at most six times, about ten minutes in all, and its sixth call passes `--final`, which turns a review still running into `timeout`.

## Results

The helper prints one JSON object whose keys are always present. Both workflows record its `summary` as the line `Tessl Review: {summary}`:

| `status` | Summary starts with | Meaning |
|---|---|---|
| `reviewed` | `reviewed — score` | Tessl finished. The scores, validation findings and suggestions are filled in. |
| `pending` | `no result yet — Tessl Review run` | Tessl accepted the review and SKF has not seen it finish. The calling step collects it again until its sixth `collect`, which reports `timeout` instead. |
| `off` | `off —` | `tessl_review_workspace` is not set. |
| `invalid-config` | `not run — tessl_review_workspace must be` | The key holds something that is not a workspace name of letters, digits, `.`, `_` and `-`. |
| `not-installed` | `not run — tessl is not installed` | Neither `tessl` nor a cached npm launcher was found. |
| `signed-out` | `not run — not signed in to Tessl` | `tessl whoami` or the review reported that the user is not signed in. |
| `command-unavailable` | `not run — the installed tessl has no working review run command` | The installed tessl lacks or replaced `tessl review run`. |
| `unknown-run` | `no result — Tessl has no review run` | `tessl review view` found no review with the run id `collect` was given, or that id is not a Tessl run id. |
| `timeout` | `no result — Tessl Review run` | SKF had not seen the review finish when the sixth `collect` ended: Tessl was still working, or its last checks failed or did not answer. The review may still complete in the workspace (`tessl review view <run id>`). |
| `failed` | `failed —` | tessl's own message, for example about the workspace, or a skill file the helper could not read, or a tessl call that did not answer in time. The steps record `failed — stopped before skf-tessl-review.py reported a result` when the shell tool stopped a helper call, and keep the run id when Tessl had accepted the review. |
| `parse-failure` | `failed — Tessl Review output could not be read` | tessl printed no review SKF can read. |

Only `reviewed` produces a score. For every other status the scores are null, and test-skill then scores External Validation from skill-check alone.

## Floors

The helper adds a warning for each of the review, description and content scores that is below 60%, and one when validation reports errors. For every status other than `reviewed` and `off` it adds the summary itself as a warning, so a review that was switched on but produced no score shows in the run's warnings. Warnings never fail a run.

## Suggestions

SKF never applies a Tessl suggestion. Content suggestions would add text SKF cannot cite to source, and the description is compiled from the brief, so a description suggestion is acted on by editing the brief and re-running create-skill. Both workflows list the suggestions as advice and mark each content suggestion that a rule below matches with `(not applicable: <rule-id>)`, because following it would break SKF's design. The judges do not know that design, so lower conciseness and progressive-disclosure scores are expected on SKF skills.

### Rule: `keep-manual-markers`

- **Matches:** removing, cleaning up or replacing `<!-- [MANUAL] -->` markers, including empty MANUAL placeholder blocks.
- **Why:** update-skill keeps the content an author writes between these markers when it regenerates the skill.

### Rule: `keep-tier2-inline`

- **Matches:** moving a `## Full …` section (API reference, type definitions, integration patterns) into a separate file while the body is within the size limit.
- **Why:** create-skill step 6 §4 moves Tier 2 sections to `references/` only when the body is over the limit, because inline context serves agents better than on-demand retrieval.

### Rule: `keep-both-tiers`

- **Matches:** merging the Key API Summary or Quick Start into the Full API Reference, or removing parameters that both list.
- **Why:** Tier 1 lists the key parameters so an agent finds them at once, and Tier 2 holds the complete tables. That is progressive disclosure, not duplication.

### Rule: `keep-provenance`

- **Matches:** removing, shortening or moving `[SRC:…]`, `[AST:…]`, `[QMD:…]` or `[EXT:…]` citations.
- **Why:** every claim carries its source, so update-skill can detect drift and audit-skill can verify the claim.

## Evolving These Rules

Add a rule when a Tessl suggestion keeps coming back that would break an SKF design principle, and name that principle in its **Why** line; a rule that protects no principle is a smell. Change the floor in the helper and here together.
