<!-- Config: communicate in {communication_language}. Render the orphan list and gate prompt in {document_output_language}. -->

# Orphan Context-File Detection — Gate Protocol

update-context.md §3b loads this gate when `orphaned_context_files` lists a known context file (`CLAUDE.md`, `.cursorrules`, `AGENTS.md`) that holds an SKF managed section while no IDE in `config.yaml` targets it.

## Gate Protocol

Emit the warning and gate:

> **Orphaned context files detected.** The following files contain SKF managed sections but no configured IDEs target them:
> {list: context file → file path}
>
> The managed sections in these files are stale. Options:
>
> - **(a) clear**: remove the SKF managed section from each orphaned file once you confirm this export's writes, leaving the content outside it intact
> - **(b) keep**: leave them untouched

Wait for user choice.

**GATE [default: b]**, headless or non-interactive: when `{headless_mode}` (or dry-run, or unattended), default to **(b) keep** and print the warning only: no destructive action without explicit consent.

When `{headless_mode}` is true, also record the decision in the run sink, listing each orphaned file's `file_path` with `/` in place of `\` so it stays a JSON string. If `record` exits non-zero, display its error line and go on (a failed `record` never stops the run):

```bash
uv run {emitEnvelopeHelper} record --workflow skf-export-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate":"update-context.orphan-context-files","default_action":"b","taken_action":"b","reason":"headless: orphaned context files kept untouched","evidence":{"files":["{file_path}"]}}
SKF_JSON
```

## Choice handling

### (a) clear

Add each file's `{context_file, file_path}` to `orphans_to_clear` and run nothing now. update-context.md §7 and §8 list each one as `{context_file}` (clear), and §9 clears it only after [C], so a cancel or a halt before §9 leaves the file as it is.

### (b) keep

Leave the files untouched, and display for each: "`{context_file}` stays as it is. To refresh it, add its IDE back to `ides` in `config.yaml` and re-run, or re-run with `--context-file {context_file}`, which writes that file alone with the skill root the IDE mapping gives it."
