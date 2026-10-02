---
# Static reference loaded by update-context.md §4c.1 only when
# `orphan_rows` is non-empty (the §4b `assemble` results list
# `[skill-name v...]` rows of the current managed sections whose skill
# neither the export manifest nor this run's batch holds). The
# reference carries the (a)/(b)/(c) gate protocol, headless default,
# deviations[] contract, and step 6 result-contract integration; the
# trigger itself stays inline in §4c.1 so the LLM knows when to invoke
# this protocol.
---

<!-- Config: communicate in {communication_language}. Render the orphan list and gate prompt in {document_output_language}. -->

# Orphan Managed-Section Rows — Gate Protocol

## Purpose

Handle the (a) Drop / (b) Preserve verbatim / (c) Cancel gate when the managed section of a target context file holds `[skill-name v...]` rows for skills that neither the export manifest nor this run's batch holds: typically externally-installed skills authored in a different repo and dropped into `{skills_output_folder}` without going through export-skill.

Strict ADR-K would silently drop such rows, but the user's managed section is load-bearing — silent removal of an installed skill is a regression. The convention captured in `skills/export-skill-result-latest.json` deviations is to make this an explicit operator (or `{headless_mode}`) choice.

## Inputs

- `orphan_rows`: the `{skill_name, version, snippet_text, source_files: [], skill_type}` entries `assemble` returned in §4b, found across **every** target context file and deduplicated by `(skill_name, version)`. `source_files` carries the file paths the orphan appeared in (one entry per file in which the row was found). `snippet_text` is the original row captured verbatim from the first file that holds it, which (b) writes back unchanged.
- `target_context_files` — the full IDE → context-file list (referenced in the gate's framing copy so the user understands the consolidation scope)
- `{headless_mode}` — boolean flag from workflow context

## Gate Protocol

Emit the gate:

> **Managed-section rows present but absent from manifest** (consolidated across {len(target_context_files)} target context file(s)):
>
> {list each as `- {skill_name} v{version} (in: {comma-separated source_files})`}
>
> These skills appear in one or more existing managed sections, but `.export-manifest.json` has no entry for them and this export does not include them. They were likely installed from a different repo and never run through export-skill in this project. Options:
>
> - **(a) Drop** — remove these rows from the rebuilt managed section across **all** target context files (strict ADR-K behavior). The skills' on-disk files are not touched, but they will no longer appear in any context file's managed index.
> - **(b) Preserve verbatim** — copy each orphan's existing snippet line(s) into the rebuilt managed section across **all** target context files unchanged (one canonical row per `(skill, version)` written everywhere — orphans become symmetric across IDEs as a side effect, which is the correct outcome since the user's intent is "these external skills should appear in my managed index"). Records `deviations[].kind = "preserve_external_skills"` with the affected skill names, versions, and `source_files` in the result contract for audit.
> - **(c) Cancel** — abort export. Before re-running, run export-skill on each of these skills that SKF generated (its `metadata.json` carries an SKF marker) to add it to the manifest, and remove the rows of the other skills from the context files yourself.

Wait for user choice.

**GATE [default: b]** (when `{headless_mode}`): auto-select **(b) Preserve verbatim**, with the same `deviations[]` entry. Emit a loud log line:

> `headless: {N} managed-section rows had no manifest entry; preserving verbatim with deviations[].kind = preserve_external_skills. Run export-skill on each skill SKF generated to add it to the manifest; remove the rows of other skills from the context files yourself.`

Record the decision in the run sink, listing each orphan row as `{skill_name} v{version}`. If `record` exits non-zero, display its error line and go on (a failed `record` never stops the run):

```bash
uv run {emitEnvelopeHelper} record --workflow skf-export-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate":"update-context.orphan-rows","default_action":"b","taken_action":"b","reason":"headless: managed-section rows with no manifest entry preserved verbatim","evidence":{"rows":["{skill_name} v{version}"]}}
SKF_JSON
```

Silent drop under automation would regress the user's managed section without consent; cancel under automation would block the whole export over an externally-installed skill the user did not author. Preservation matches the prior-attentive-operator convention.

## Choice handling

### (a) Drop

Run update-context.md §4b again for every target with `--orphans drop`, so no rebuilt section holds an orphan row. Record:

```
orphans_dropped = [{skill_name, version}, …]
```

in workflow context for the step 6 result contract.

### (b) Preserve verbatim

Keep the bodies §4b staged: `assemble` already wrote each orphan's `snippet_text` into them verbatim, sorted with the other rows by skill name, **once** per section, and counted it as a stack skill when its row has a `|stack:` line. Nothing is merged by hand.

Append the following entry to the `deviations[]` array in the step 6 result contract:

```json
{
  "kind": "preserve_external_skills",
  "skills": [
    {"name": "...", "version": "...", "source_files": ["..."]}
  ],
  "rationale": "managed-section row exists but no manifest entry / no source draft"
}
```

`source_files` per skill records the prior context files the orphan was found in (asymmetric provenance preserved for audit) — useful when an operator later debugs which IDE's managed section originally carried the row.

Every §4b call scans every target file in the same order, so the same orphans are written to **every** target context file: all configured IDEs end up with consistent managed sections (asymmetric prior orphans become symmetric, the correct outcome for the "preserve external skills" intent).

### (c) Cancel

HALT the workflow:

- Do not rewrite any context file.
- Do not update the manifest.
- Do not produce a result contract.
- Delete the `{export_stage_dir}` folder, as every exit from update-context.md does.
- Exit code 6, `halt_reason: "user-cancelled"` (matches the §8 Menu cancel semantics).
- In headless mode this branch is never taken (headless default is (b)), so this exit path is interactive-only.

## Downstream contract

After this protocol completes, §4c.1 returns control to §5 with these workflow-context variables populated:

- `orphans_dropped: []`: set when the user chose (a), else empty
- `deviations[]` — extended with the `preserve_external_skills` entry when the user chose (b)
- The staged bodies hold the orphan rows verbatim when (b) was chosen, and leave them out when (a) was chosen

## Scope note

This gate runs once per export run, not per target context file: every §4b call passes every target file as `--orphan-sources`, so each result lists the same orphans, deduplicated by `(skill_name, version)`. The gate's choice applies globally, and asymmetric orphans (a row present in `.cursorrules` but not in `CLAUDE.md`, or vice versa) are detected and surfaced with `source_files` provenance.
