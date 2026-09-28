---
title: Campaign Orchestration
description: Multi-library skill production with dependency tracking, file-based state, and resume
---

Campaign orchestration builds many related skills as one coordinated campaign, in dependency order. It is meant for projects with many libraries (15 or more), but one library is enough to start. Each Tier A library goes through the full SKF pipeline: analyze, brief, compile and test. Tier B libraries take a faster batch path. The finished skills are exported together at the end (see [Tier A vs Tier B](#tier-a-vs-tier-b)). The `skf-campaign` skill does not write skills itself. It runs the SKF workflows that do, in the right order.

When your project depends on many libraries, building one skill at a time is slow and easy to get wrong. Campaign runs the whole loop for you. You list the libraries and what each one depends on, and Campaign orders them so every skill is built after the skills it depends on. It then drives each one through the pipeline, applies the quality gates, and saves its progress to disk as it goes. If the AI session runs out of context or you close it, you can resume where you left off.

---

## Before You Start

- Run `skf-setup` first, so SKF knows your tools and folders.
- Install the GitHub CLI (`gh`) and sign in. Pin Validation and Provenance use it to check every repository, and without it the campaign stops before any skill is built. Each library's repository must be on GitHub.
- An architecture document is optional. Only the Verification and Refinement stages use it (see [Stages](#stages)).

---

## Invocation

Ask Ferris to run `campaign`, or call the `skf-campaign` skill directly.

```
@Ferris campaign                          # start a new campaign
@Ferris campaign resume                   # resume from the last active skill
@Ferris campaign resume --from=<skill>    # resume from a specific skill
@Ferris campaign status                   # read-only progress summary
```

- **`campaign`** starts a new campaign from stage 0 (Setup). If a `_campaign-state.yaml` already exists, Ferris offers a choice: resume the existing campaign or overwrite with a new one.
- **`campaign resume`** picks up where the last session left off. Ferris checks the state file first. If it is damaged, Ferris restores the `.bak` backup copy and continues from that.
- **`campaign status`** checks the state file and shows the campaign name, the current stage, how many skills are done out of the total, and how many skills have each status. After that come the last lines of the decision log. Then it stops. It makes no backup, changes nothing and starts no stage, so you can check on a long campaign without moving it forward.
- **`--from=<skill>`** moves the resume point to the named skill. To rebuild a skill that already finished, choose `[R]e-run` when Ferris asks.

### Override flags

| Flag | Effect |
|------|--------|
| `--headless` / `-H` | Answer every question with its default and print machine-readable progress and results (see [Headless / Automation](#headless--automation)). |
| `--brief <file>` | Seed targets from a `campaign-brief.yaml` instead of interactive prompts. Implies `--headless`. |
| `--manifest <file>` | Seed targets from a plain-text `name,repo_url,tier,pin` manifest (one per line; trailing `;dep1,dep2` for `depends_on`). Implies `--headless`. |
| `--from=<skill>` | Resume override (see above). |

### What Setup Asks For

Setup asks for a campaign name and, for each library:

- `name`: the skill name
- `repo_url`: the GitHub repository
- `tier`: `A` (full pipeline) or `B` (quick batch), see [Tier A vs Tier B](#tier-a-vs-tier-b)
- `pin`: a version tag or branch, or empty for the latest release
- `depends_on`: the other skills in this campaign that it depends on

You can also give the path to a `_campaign-directive.md` file and to your architecture document. Setup then asks whether to send anonymized quality findings to the shared improvement queue; the default is no.

To skip these questions, pass the list as a manifest file with `--manifest`:

```
# name,repo_url,tier,pin;depends_on
core-lib,https://github.com/acme/core-lib,A,
web-sdk,https://github.com/acme/web-sdk,A,2.1.0;core-lib
cli-helpers,https://github.com/acme/cli-helpers,B
```

If any line is malformed, Setup stops with exit code 2 and lists the bad line numbers. It never runs with only part of the list.

---

## Stages

Campaign runs through 11 stages, numbered 0 to 10. Most run on their own. Setup asks for your campaign details, unless you pass `--brief` or `--manifest`. Two stages always stop for your answer: Strategy shows you the plan before any skill is built, and Export asks before it writes anything. The Skill Loop, Verification and Refinement ask only when they need a decision. In headless mode, every question takes its default answer.

| Stage | Name | What happens | Waits for you? |
|-------|------|--------------|----------------|
| 0 | Setup | Asks for the campaign name and the libraries to skill, writes `_campaign-state.yaml`, and generates `campaign-brief.yaml` | Yes, for its questions (not with `--brief` or `--manifest`) |
| 1 | Strategy | Works out the build order so each skill comes after the skills it depends on, stops on a circular or unknown dependency, and shows you the plan | Yes: `[P]roceed` or `[C]ancel` |
| 2 | Pin Validation | Checks every version pin against the repository's real releases and branches, and fills an empty pin with the latest release | No |
| 3 | Provenance | Checks that every repository is reachable and records the exact commit each skill is built from | No |
| 4 | Skill Loop | Builds each Tier A skill in order through analyze (AN), brief (BS), compile (CS) and test (TS). Export waits for stage 9 | Only when a skill's dependencies have not completed |
| 5 | Tier B Batch | Builds every Tier B skill in one Quick Skill batch run (`skf-quick-skill --batch`) | No |
| 6 | Capstone | Composes one stack skill from all completed skills, using `skf-create-stack-skill` in compose mode | No |
| 7 | Verification | Runs `skf-verify-stack` against your architecture document and records the overall verdict and coverage it reports | Only to ask for a missing architecture document |
| 8 | Refinement | Runs `skf-refine-architecture`, which writes a refined copy of your architecture document based on the skills | Only to ask for a missing architecture document |
| 9 | Export | Lists every completed skill and, once you approve, runs `skf-export-skill` on each one to package it and update your context files | Yes: `[E]xport all` or `[C]ancel` |
| 10 | Maintenance | Writes `campaign-report.md`, runs your `on_complete` hook if you set one, then runs the end-of-workflow health check | No |

Verification and Refinement use the architecture document path you gave at Setup. Without one, they look for `docs/architecture.md` and then `_bmad-output/planning-artifacts/architecture.md`. A headless run with no architecture document skips both stages. If either stage fails, the failure is logged and the campaign carries on.

---

## Key Concepts

### campaign-brief.yaml

A machine-readable summary of the campaign, written during Setup from what you enter (or from `--brief` or `--manifest`). It holds the campaign name; each library's repository URL, tier, version pin and dependencies; the quality gate; where health findings go; the architecture document path; and your notes. Later stages read the repository URLs from it, and a fresh session uses it to pick the campaign back up.

### _campaign-state.yaml

The single source of truth for campaign progress. Every change follows a read, back up, modify, write pattern: the current state is copied to `_campaign-state.yaml.bak` before each write, so a crash during a write loses at most that one change. All progress lives in this file, not in the conversation.

### _campaign-directive.md

An optional Markdown file of standing instructions for the whole campaign. You give its path at Setup. Each stage that uses it re-reads it when the stage starts, so edits you make between stages take effect. It can hold `## Quality Overrides`, `## Skip List`, `## Pipeline Flags` and `## Notes` sections, and any other heading is read as general guidance. See the [campaign directive spec](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-campaign/references/campaign-directive-spec.md) for the full format.

### Where Campaign Files Live

Everything the campaign writes about itself sits in one folder: `forge-data/_campaign/` by default (`{forge_data_folder}/_campaign`). It holds `_campaign-state.yaml` and its `.bak` backup, `campaign-brief.yaml`, the decision log, the Tier B batch input, the `archive/` folder and `campaign-report.md`. To move it, set `campaign_workspace_path` (see [Customization](#customization)).

### _campaign-decision-log.md

This log only grows. It records every decision in the campaign, whether you made it or a headless run took the default: skip or force at a dependency gate, overwrite, export or cancel at the Export gate, recovery from the backup, a cancel at any other question, and why a skill failed. `campaign status` shows its last lines.

### Dependency Tracking

Campaign orders skills by their `depends_on` lists, so if skill B depends on skill A, skill A is built first. A dependency counts as met only when that skill has completed. If it has not, the Skill Loop stops at the waiting skill and asks you to `[S]kip` it, `[F]orce` it anyway, or `[H]alt`; headless runs halt. A circular or unknown dependency stops the campaign at Strategy with exit code 4.

### Tier A vs Tier B

You choose a tier for each library at Setup.

- **Tier A** gets the full pipeline during the Skill Loop: analyze (AN), brief (BS), compile (CS) and test (TS). The tested skills are exported together at the Export stage.
- **Tier B** is built in one batch by Quick Skill (`skf-quick-skill --batch`) during the Tier B Batch stage. It is faster and gives best-effort skills, with no separate test step.

Do not make a Tier A library depend on a Tier B library. A dependency counts as met only once that skill has completed, and Tier B skills are built after the Skill Loop, so the Tier A skill would stop at the dependency gate.

### Customization

Campaign ships a `customize.toml` file that you can tune without forking the skill. When the campaign starts, it merges three layers: the bundled `customize.toml`, then a team override committed at `_bmad/custom/skf-campaign.toml`, then a personal override at `_bmad/custom/skf-campaign.user.toml` that git ignores. Both overrides sit under your project root. A single value in a later layer replaces the earlier one, and list entries add up. You can set:

- **Quality-gate values**: `quality_gate_hard`, `quality_gate_soft_target` and `quality_gate_soft_fallback` (see [Quality Gates](#quality-gates) below).
- **`campaign_workspace_path`**: moves the whole campaign folder (state, backup, brief, batch input, archive, report and decision log), for example to a shared volume. Empty means the default, `{forge_data_folder}/_campaign`.
- **`persistent_facts`**: plain sentences or `file:` references (globs allowed) added to every skill's kickoff message, so house style and guardrails reach the whole campaign. By default it loads every `project-context.md` in your project.
- **Template overrides**: `report_template_path`, `kickoff_template_path` and `brief_template_path` point to your own copies of the templates.
- **`on_complete`**: a command run with `--report-path=<path>` after the report is written. If it fails, the failure is logged and the campaign still succeeds.
- **`activation_steps_prepend` / `activation_steps_append`**: extra steps run before or after activation, for org-wide checks or loading context.

These overrides need BMAD Method's customization script, which the BMAD Method installer adds. In a project with SKF alone, the campaign ignores `_bmad/custom/` and uses the bundled values. See [Workflows: Customizing a Workflow](/docs/workflows.md#customizing-a-workflow) for the settings every workflow shares.

See the skill's [SKILL.md](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-campaign/SKILL.md) for the full merge contract.

---

## Quality Gates

One quality bar applies to every skill in the campaign. It has three parts:

- **Hard gate** (`zero-critical-high`): a skill may have no critical or high-severity findings. The test step (`skf-test-skill`) fails a skill that has any. The campaign marks that skill failed and writes the reason to the decision log. Skills that depend on it wait at the dependency gate, and the other skills carry on.
- **Soft target** (default 90%): the score a skill should reach.
- **Soft fallback** (default 80%): the floor. A skill that scores at or above the fallback but below the target still passes. A skill below the fallback fails.

You can change all three through [customization](#customization). The campaign brief and a directive's `## Quality Overrides` section take precedence when the campaign runs. The campaign gives these values to each skill's pipeline as its quality target and prints them in the report. The pass or fail verdict itself comes from `skf-test-skill`, whose fallback floor is fixed at 80%, so changing `quality_gate_soft_fallback` does not move that floor.

---

## Resume

Campaign expects the AI session to end before the campaign does, for example when it runs out of context. Its progress lives on disk in `_campaign-state.yaml`, so it survives a lost session, a timeout or a machine restart.

When you resume:

1. Ferris validates the state file against the campaign schema
2. Completed skills are skipped automatically
3. If a skill was in progress, the campaign returns to it (the Skill Loop for Tier A, the Tier B Batch for Tier B). Otherwise it starts the stage after the last stage that finished
4. All cross-skill context (dependency graph, quality scores, provenance records) is restored from disk

Use `--from=<skill>` to resume at a specific skill. If that skill already finished (completed, failed or skipped), Ferris asks whether to `[R]e-run` it, jump to the `[N]ext` unfinished skill, or `[H]alt`. Headless runs take `[N]ext`, so they never re-run a finished skill. An unknown skill name stops the campaign with exit code 2.

### Re-invocation and recovery

- **Running `campaign` when a state file already exists** asks whether to resume or overwrite. Overwrite first moves the existing `_campaign-state.yaml` and `campaign-brief.yaml` into `archive/{name}-{timestamp}/` and records this in the decision log, so a new campaign never silently replaces an old one. Headless runs resume by default; they archive and overwrite only when `--brief` or `--manifest` seeds a new campaign.
- **Damaged state file, good backup**: resume restores the `.bak` copy over the state file and logs the recovery. If the backup is also unusable, the campaign stops with exit code 9 (`corrupt-state`) and reports both errors.
- **State file older than its backup**: this can happen after a crash during the last write. Ferris offers `[R]ecover` from the backup or `[K]eep` the state file. `[K]eep` is the default, and headless runs keep it.

---

## Expected Output

A finished campaign leaves:

- **Individual skills**: one for each library that completed, exported at the Export stage.
- **One capstone stack skill**: composed from all completed skills. The Export stage exports only the individual skills, so run `skf-export-skill` on the stack skill yourself when you want it packaged.
- **Verification report and refined architecture**: from Verification and Refinement, when an architecture document was found.
- **Campaign report** (`campaign-report.md`): the quality gate; a table of every skill with its tier, status, score, pin and workarounds; the lowest, highest and average scores; time per skill; and a section on failed or skipped skills.
- **Decision log** (`_campaign-decision-log.md`): every decision made during the campaign.
- **Headless result line** (`SKF_CAMPAIGN_RESULT_JSON`): printed in headless mode for scripts to read.

The Export stage (stage 9) asks before it writes anything. It lists every completed skill and waits for `[E]xport all` or `[C]ancel`. In headless mode it exports without asking.

---

## Headless / Automation

Campaign can run unattended across several sessions. Add `--headless` / `-H`, or set `headless_mode: true` in `_bmad/_memory/forger-sidecar/preferences.yaml`. `--brief` and `--manifest` turn headless mode on for you and supply the targets. In headless mode every question takes its default answer. Each step prints a one-line JSON progress event to **stderr** when it starts and when it ends (`{"stage":N,"name":"<slug>","status":"start|done"}`), or `{"stage":N,"name":"<slug>","status":"halt","exit":<code>}` when it stops on an error. The last step prints the `SKF_CAMPAIGN_RESULT_JSON` line on stdout.

- **Cancel**: at any question between Setup and the Export gate, type `cancel`, `exit` or `:q` to stop cleanly. The campaign stops with exit code 12 (`user-cancelled`), logs the cancel, and leaves its state ready to resume. The Export gate is the exception: its own `[C]ancel` exits with code 11 (`export-cancelled`).
- **Exit codes**: every stop on an error exits with a fixed code, so scripts can branch on the kind of failure without reading the message: `0` success, `2` invalid-input (for example no targets, a malformed manifest line, `gh` not available, or an unknown `--from` skill), `3` invalid-state, `4` circular-deps, `5` invalid-pin, `6` inaccessible-repo, `7` dependency-deadlock, `8` missing-brief, `9` corrupt-state, `10` report-failure (the campaign still completes; only the report is missing), `11` export-cancelled, `12` user-cancelled.
- **Error line**: when the campaign stops on an error, it prints the `SKF_CAMPAIGN_RESULT_JSON` line on stderr in its error form. The line carries `status: "error"`, `exit_code`, `phase` (the step where it stopped), and an `error` object holding `code` and `message`.

The full exit-code table and result-line formats are in the skill's [campaign contracts](https://github.com/armelhbobdad/bmad-module-skill-forge/blob/main/src/skf-campaign/references/campaign-contracts.md), under "Exit Codes" and "Result Contract on HARD HALT".

---

## Timing

Campaign time grows with the number of libraries. Each Tier A skill runs the full analyze, brief, compile and test chain, and Tier B skills run in one batch. A campaign is meant to **span several sessions**: its state is on disk, so you can stop after any skill and resume later without losing progress. What affects total time:

- **Skill count and tier mix**: Tier A skills, each with a full pipeline, take most of the time. Tier B batch processing is lighter per skill.
- **Dependency depth**: in a deep chain of dependencies, each skill waits for the ones before it. A wide, shallow graph splits more easily across sessions.
- **Capstone breadth**: composing the stack skill (stage 6) takes longer the more skills it combines.
- **Forge tier**: at Deep tier (ast-grep, GitHub CLI and QMD), each skill spends more time on QMD knowledge search.

Plan a campaign as work over several sessions, not one sitting. The campaign saves its state to disk as it goes, so losing the session between skills costs you nothing.

---

## Related

- [Workflows](/docs/workflows.md): pipeline mode, headless mode and circuit breakers
- [forge-auto](/docs/forge-auto.md): one command that builds and exports a single skill. A campaign runs a similar chain for each Tier A library and exports them together at the end
- [BMAD Synergy](/docs/bmad-synergy.md): where campaign fits in BMAD Phase 3 (Solutioning)
