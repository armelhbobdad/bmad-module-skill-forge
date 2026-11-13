<!-- Config: communicate in {communication_language}. Render the orphan list and gate prompt in {document_output_language}. -->

# Orphan Managed-Section Rows — Gate Protocol

update-context.md §4c.1 loads this gate when `orphan_rows` lists managed-section rows whose skill neither the export manifest nor this run's batch holds, each deduplicated by `(skill_name, version)` across every target context file, with the `source_files` it was found in.

## Gate Protocol

Emit the gate:

> **Managed-section rows present but absent from manifest** (consolidated across {len(target_context_files)} target context file(s)):
>
> {list each as `- {skill_name} v{version} (in: {comma-separated source_files})`}
>
> These skills appear in one or more existing managed sections, but `.export-manifest.json` has no entry for them and this export does not include them. They were likely installed from a different repo and never run through export-skill in this project. Options:
>
> - **(a) Drop** — remove these rows from the rebuilt managed section across **all** target context files (strict ADR-K behavior). The skills' on-disk files are not touched, but they will no longer appear in any context file's managed index.
> - **(b) Preserve verbatim**: copy each orphan's existing snippet line(s) into the rebuilt managed section across **all** target context files unchanged.
> - **(c) Cancel** — abort export. Before re-running, run export-skill on each of these skills that SKF generated (its `metadata.json` carries an SKF marker) to add it to the manifest, and remove the rows of the other skills from the context files yourself.

Wait for user choice.

**GATE [default: b]** (when `{headless_mode}`): auto-select **(b) Preserve verbatim**. Emit a loud log line:

> `headless: {N} managed-section rows had no manifest entry; preserving verbatim with deviations[].kind = preserve_external_skills. Run export-skill on each skill SKF generated to add it to the manifest; remove the rows of other skills from the context files yourself.`

Record the decision in the run sink, listing each orphan row as `{skill_name} v{version}`. If `record` exits non-zero, display its error line and go on (a failed `record` never stops the run):

```bash
uv run {emitEnvelopeHelper} record --workflow skf-export-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate":"update-context.orphan-rows","default_action":"b","taken_action":"b","reason":"headless: managed-section rows with no manifest entry preserved verbatim","evidence":{"rows":["{skill_name} v{version}"]}}
SKF_JSON
```

## Choice handling

### (a) Drop

Run update-context.md §4b again for every target with `--orphans drop`, so no rebuilt section holds an orphan row, and bind `orphans_dropped` ← `orphan_rows`, which summary.md §6 records as `drop_external_skills`.

### (b) Preserve verbatim

Keep the bodies §4b staged: `assemble` already wrote each orphan's `snippet_text` into them verbatim, sorted with the other rows by skill name, **once** per section, and counted it as a stack skill when its row has a `|stack:` line. Nothing is merged by hand. Bind `orphans_preserved` ← `orphan_rows`, which summary.md §6 records as `preserve_external_skills`.

Every §4b call scans every target file in the same order, so the same orphans are written to **every** target context file: all configured IDEs end up with consistent managed sections (asymmetric prior orphans become symmetric, the correct outcome for the "preserve external skills" intent).

### (c) Cancel

HALT the workflow:

- Do not rewrite any context file.
- Do not update the manifest.
- Do not produce a result contract.
- Delete the `{export_stage_dir}` folder, as every exit from update-context.md does.
- Exit code 6, `halt_reason: "user-cancelled"` (matches the §8 Menu cancel semantics).
- In headless mode this branch is never taken (headless default is (b)), so this exit path is interactive-only.
