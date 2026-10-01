---
# Loaded by load-skill.md §1b, once per run, only when config.yaml sets no
# `snippet_skill_root_override`.
---

<!-- Config: communicate in {communication_language}. Render the question, the warning and the gate prompt in {document_output_language}. -->

# Snippet Root Probe

## Purpose

Decide where the managed section points each skill before step 3 writes a `root:` path. A consuming project points at its IDE's skill folder (`.claude/skills/`, `.cursor/skills/` and so on), where `npx skills add` installs each skill. An authoring repo keeps its skills in one shared folder, such as `skills/`, and sets `snippet_skill_root_override` in `config.yaml`. Only a root an earlier export chose shows the layout: create-skill, create-stack-skill, quick-skill and update-skill write the draft root `skills/{skill-name}/` into every snippet they build, whatever the layout. So a repo whose skills live in `skills/` sets `snippet_skill_root_override: skills/`: a `skills/{skill-name}/` root an earlier export wrote reads as a draft root, and without the override the probe asks the Layout Question, whose headless default is the IDE skill folder.

`{reference_root}` is `target_context_files[0].skill_root`, the root step 3 writes when nothing overrides it.

## Probe

List the snippet of each version the export manifest records: for each skill in step 1 §1's `result.manifest.exports` whose `active_version` has an entry under `versions`, `{skills_output_folder}/{skill-name}/{active_version}/{skill-name}/context-snippet.md`. A skill the manifest does not list was never exported, so its snippet holds the draft root only. With no snippet to list, go to the Layout Question. Otherwise run:

```bash
python3 {rebuildManagedSectionsHelper} root-probe {snippet-1} {snippet-2} … --reference-root "{reference_root}" --project-root "{project-root}"
```

The helper reads each snippet's `root:` prefix and leaves out a snippet that is missing, has no root, or holds the draft root (it lists those skills in `draft_roots`). It returns `observed_prefixes`, `mismatch` (true when one of them is not `{reference_root}`), `mismatched_skills`, and `disk_root`: `{reference_root}` when that folder holds every mismatched skill, else the one observed prefix when that folder holds them all, else null. Then:

- `observed_prefixes` is empty: no earlier export chose a root. Ask the Layout Question.
- `mismatch` is false: every earlier export chose `{reference_root}`. Ask nothing and return to load-skill.md §1b.
- `mismatch` is true: take the Mismatch Gate.

## Layout Question

> **Where should the managed section point your skills?** No earlier export has chosen yet. By default each row points at `{reference_root}{skill-name}/`, your IDE's skill folder, where `npx skills add` installs the skill (step 6 prints the command).
>
> - **[I] IDE skill folder** (default): point at `{reference_root}`.
> - **[S] Shared skills folder**: point at the skills where SKF writes them, for a repo that keeps them there. Export, drop-skill and rename-skill read that choice from `config.yaml`.
> - **[X] Cancel**

Wait for the user's choice.

- **[I]**: return to load-skill.md §1b.
- **[S]**: display "Add `snippet_skill_root_override: {skills_prefix}` to `{project-root}/_bmad/skf/config.yaml`, then re-run the export." and HALT (exit code 6, `halt_reason: "user-cancelled"`): the workflow never edits `config.yaml`. `{skills_prefix}` is the path of `{skills_output_folder}` from `{project-root}`, with a trailing `/`, such as `skills/`.
- **[X]** / `cancel` / `exit` / `:q`: HALT (exit code 6, `halt_reason: "user-cancelled"`). Nothing was written.
- **Headless** [default I]: record the decision in the run sink with the command below, log "headless: no earlier export chose a snippet root, using the IDE skill folder", then take [I]. If `record` exits non-zero, display its error line and go on: a failed `record` never stops the run.

```bash
uv run {emitEnvelopeHelper} record --workflow skf-export-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate":"load-skill.snippet-root-layout","default_action":"I","taken_action":"I","reason":"headless: no earlier export chose a snippet root, using the IDE skill folder","evidence":{"reference_root":"{reference_root}"}}
SKF_JSON
```

## Mismatch Gate

> **Snippet root prefix mismatch detected.**
> Earlier exports point at: `{observed_prefixes}`
> The IDE mapping points at: `{reference_root}`
>
> - **(a) Set override**: add `snippet_skill_root_override: {observed_prefix}` to `config.yaml`, which export, drop-skill and rename-skill all read. Snippets keep their on-disk prefix.
> - **(b) Proceed with IDE mapping**: every row's root becomes `{reference_root}`. Use this when that folder holds the skills, or will once you install them there.
> - **(c) Cancel**: abort the export and investigate.
> - **(d) Use the observed prefix for this run only**: every row's root stays `{observed_prefix}`, and `config.yaml` is not changed. (Offered only when exactly one prefix was observed.)
>
> If several prefixes were observed, the snippets disagree with each other: investigate before choosing (a).

Wait for the user's choice.

**Headless default, by the disk:** take (d) when `disk_root` is the observed prefix (that folder holds the skills and `{reference_root}` does not), else (b): `{reference_root}` holds them, or no folder does yet, as in a project that installs its skills after the export. `{choice}` is the option taken. Log it with the observed prefixes, record the decision in the run sink with the command below (`{disk_root}` is `none` when it is null), then take that option. If `record` exits non-zero, display its error line and go on: a failed `record` never stops the run.

```bash
uv run {emitEnvelopeHelper} record --workflow skf-export-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate":"load-skill.snippet-root-probe","default_action":"{choice}","taken_action":"{choice}","reason":"headless: snippet root prefix mismatch, option {choice} by the folder on disk that holds the skills","evidence":{"observed_prefixes":{observed_prefixes},"reference_root":"{reference_root}","disk_root":"{disk_root}"}}
SKF_JSON
```

### Choice handling

- **(a) Set override**: display "Add `snippet_skill_root_override: {observed_prefix}` to `{project-root}/_bmad/skf/config.yaml`, then re-run the export." and HALT (exit code 6, `halt_reason: "user-cancelled"`): the workflow never edits `config.yaml`.
- **(b) Proceed with IDE mapping**: return to load-skill.md §1b. Step 4 writes `{reference_root}` as every row's root.
- **(c) Cancel**: HALT (exit code 6, `halt_reason: "user-cancelled"`). Nothing was written.
- **(d) Use the observed prefix for this run only**: bind `{snippet_skill_root_override}` ← the observed prefix for this run, without editing `config.yaml`. Step 3 §2.7 and step 4 §4b read it as they read the `config.yaml` value, so every snippet and row keeps that root. Display "Persist `snippet_skill_root_override: {observed_prefix}` in `{project-root}/_bmad/skf/config.yaml` to skip this question next time: drop-skill and rename-skill read only `config.yaml` when they rebuild the section." Return to load-skill.md §1b.
