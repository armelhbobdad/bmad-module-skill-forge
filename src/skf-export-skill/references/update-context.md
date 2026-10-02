---
nextStepFile: 'token-report.md'
# SKILL.md's On Activation resolved {rebuildManagedSectionsHelper}, which
# builds and writes every managed section (`assemble` builds each body,
# `check` picks the write and enforces the malformed-marker halt, `read`
# shows the old section, `insert` / `replace` write atomically and verify),
# and {manifestOpsHelper}, whose `set` records each skill in §9b.
---

<!-- Config: communicate in {communication_language}. Render the change preview and managed section in {document_output_language}. -->

# Step 4: Update Context

## STEP GOAL:

To update the SKF managed section in each target context file (CLAUDE.md, AGENTS.md or .cursorrules) through `skf-rebuild-managed-sections.py`, which builds the section from every exported skill and writes it by the four cases of ADR-J (Create, Append, Regenerate, Malformed Markers halt), to record every skill of the batch in the export manifest, and then to write each skill's staged `context-snippet.md` into its package.

## Rules

- The helper builds and writes the section: never type a snippet, a marker or a date into a context file, and never change the content outside the markers
- Do not write a context file without user confirmation (§8): this modifies shared project files, and a dry run writes none
- If `passive_context: false` was detected in step 1, skip to §9b: the export manifest still records the export
- **Multi-skill mode:** this step runs once for the whole batch: each body lists every skill in `skill_batch` (§4a), one gate confirms every target (§8), §9b records every skill, and §9c writes each skill's snippet. See step 1 §1c.
- Every HALT names its exit code, `halt_reason` and phase; in headless mode it first emits its envelope as `references/result-envelope.md` states

## MANDATORY SEQUENCE

### 1. Check Passive Context Setting

**If `passive_context: false` was detected in step 1:**

"**Passive context disabled in preferences.yaml. Skipping the context files; the export manifest still records this export.**"

Run §9b, then auto-proceed to {nextStepFile}.

**If `passive_context: true` (default):** Continue to §2.

### 2. Stage Folder

Step 3 bound `{export_stage_dir}`, the run's folder outside the project that holds each skill's snippet draft under `drafts/`. This step stages each target's new section body under its `previews/` folder, so nothing lands beside a context file before the §8 gate, and deletes the folder on every exit: the §8 dry run and cancel, the end of §9c, the orphan-row (c) Cancel and every HALT in this step.

### 3. Determine Target Files

Step 1 resolved `target_context_files` through `resolve-targets`: one `{context_file, skill_root, ides}` entry per file. Process the targets in that order. A context file's path is `{context_path}`, its `{context_file}` in `{project-root}`, its skill root `{target_skill_root}` is that entry's own `skill_root`, and `{target_paths}` is the `{context_path}` of every target, each quoted, space-separated, in that order.

#### 3b. Detect Orphaned Platform Files (Stale Managed Sections)

A context file becomes orphaned when its IDE is removed from `config.yaml` after a prior export: it still holds an SKF managed section that lists stale skill versions, but no later export rewrites it.

Run `check` on each file of step 1's `{other_context_files}`, the known context files no configured IDE maps to:

```bash
python3 {rebuildManagedSectionsHelper} "{context_path}" check
```

A file whose `case` is `regenerate` holds a managed section: add `{context_file, file_path}` to `orphaned_context_files`, with its `{context_path}` as `file_path`. A `malformed` one is left as it is, with the warning "`{context_file}` has malformed SKF markers, so it was left as it is: {error}". Any other case is not orphaned.

**If `orphaned_context_files` is non-empty:** load `references/orphan-context-detection.md` and follow its (a) clear / (b) keep / (c) rewrite gate protocol. It handles user prompting, the headless default (keep), and the state it records (`orphans_cleared`, `orphans_rewritten`, `rewrite_context_files`). Each file the user chose to rewrite joins the targets for §4 to §9, with `.agents/skills/` as its skill root and no IDEs, and `{target_paths}` lists it too.

**If `orphaned_context_files` is empty:** proceed to §4.

### 4. Build the Managed Section

#### 4a. The Skills It Lists

`assemble` lists each skill of the export manifest whose active version is not deprecated and, through `--include`, every skill in `skill_batch` at the version in its `{resolved_skill_package}/metadata.json`, so a first export, a batch member the manifest does not list yet, and a skill the step 1 manifest-lag guard resolved to a newer version all appear at the version this export publishes. Bind `{batch_includes}` to the comma-joined `{skill-name}@{version}` of every skill in `skill_batch`. `--snippet-dir` hands it the drafts step 3 staged, so a batch skill's row is its new snippet.

#### 4b. Assemble One Body per Target

For each target, run:

```bash
python3 {rebuildManagedSectionsHelper} assemble "{context_path}" \
  --skills-folder "{skills_output_folder}" --skill-root "{target_skill_root}" \
  --include {batch_includes} --snippet-dir "{export_stage_dir}/drafts" \
  --orphan-sources {target_paths} --orphans {orphan_mode} \
  --out "{export_stage_dir}/previews/{context_file}.skf-content" \
  [--skill-root-override "{snippet_skill_root_override}"]
```

Add `--skill-root-override` only when `{snippet_skill_root_override}` is set (by `config.yaml`, or for this run by step 1's snippet-root option (d)). `{orphan_mode}` is `keep` unless §4c.1 drops the orphan rows. The helper writes the body to the `--out` file, with no marker and no trailing newline, and prints its result as JSON. From each target's result bind `{content_file}` ← `content_file`, `{n_single}` ← `n_single` and `{n_stack}` ← `n_stack`. A non-zero exit writes nothing: HALT (exit code 4, `halt_reason: "context-rebuild-failed"`, phase `update-context §4b`) and report `{context_file}: {error}` (for example a context file that is not UTF-8 text: the error says how to fix it).

When the first result's `malformed_context_files` is not empty, run the §5 `check` on those files now and take its `malformed` HALT, before §4c.1 asks anything: a target whose `<!-- SKF:BEGIN` marker no `<!-- SKF:END -->` closes is never written.

#### 4c. Report What Was Left Out

Every call reads the same manifest and snippets, so report these once, from the first result:

- each `skipped_integrity[]` entry: "**Manifest integrity warning:** `{skill_name}`: {reason}. Skipping. Re-run `[EX] Export Skill` on `{skill_name}` to repair the manifest entry."
- each `skipped_deprecated[]` entry: "Skipping {skill_name}: active version v{version} is deprecated"
- each `skipped_missing_snippet[]` entry: "Snippet missing for {skill_name} v{version}: skipping from managed section"
- each `skipped_malformed_snippet[]` entry: "Snippet of {skill_name} v{version} skipped: {reason}"
- each `warnings[]` line as it is

With no skill to list, each body holds the header alone (`0 skills|0 stack`).

#### 4c.1 Orphaned Managed-Section Rows

A managed-section row is orphaned when the export manifest has no entry for its skill and this run does not export it: typically a skill installed from another repo into `{skills_output_folder}` without going through export-skill. Strict ADR-K would drop such a row, but the row is often the only copy of that skill's snippet, so the helper keeps it verbatim unless told to drop it, and lists it in `orphan_rows` (each with `skill_name`, `version`, `snippet_text` and `source_files`). Every call scans the same files in the same order, so bind `orphan_rows` from the first result.

**If `orphan_rows` is non-empty:** load `references/orphan-row-detection.md` and follow its (a) Drop / (b) Preserve verbatim / (c) Cancel gate protocol. It handles user prompting, the headless default (Preserve verbatim), the `deviations[]` record and the result-contract integration. On (a), run §4b again for every target with `--orphans drop`.

**If `orphan_rows` is empty:** proceed to §5.

### 5. Check Each Target File

Run `check` on each target:

```bash
python3 {rebuildManagedSectionsHelper} "{context_path}" check
```

Bind `{case}` ← `case` for that target. The case picks the §9 write:

| `case` | The target file | §9 write |
|---|---|---|
| `create` | does not exist | `insert`, which creates it with the section |
| `append` | has no managed section | `insert`, which adds the section at its end |
| `regenerate` | has a managed section | `replace`, which swaps that section and keeps everything outside the markers |
| `malformed` | has a `<!-- SKF:BEGIN` marker that no `<!-- SKF:END -->` closes | none: HALT |

- **`malformed`:** HALT (exit code 5, `halt_reason: "malformed-markers"`, phase `update-context §5`) with the helper's `error`, which names the line of the marker and the fix (restore the `<!-- SKF:END -->` line, or remove the stray `<!-- SKF:BEGIN`, then re-run). Write nothing to any target: the helper refuses such a file, because a write there would take the user's lines below the marker for part of the section.

### 6. Read the Current Sections

For each `regenerate` target, read the section §9 replaces:

```bash
python3 {rebuildManagedSectionsHelper} "{context_path}" read
```

Bind `{old_section}` ← `content` for that target; §7 shows it beside the new body.

### 7. Present Change Preview

"**Context update prepared.{if multi-platform: ' (platform {i}/{total}: {platform})'}**

**Target:** `{context_file}`
**Case:** {Create / Append / Regenerate}
**Skills in index:** {n_single} skills, {n_stack} stack

**Changes:**

{Show the diff preview from the new body in `{content_file}`:}
- For Create: the new file, which holds only the section
- For Append: `...existing content preserved...` followed by the section
- For Regenerate: `{old_section}` beside the new body, with the content outside the markers preserved

**Content outside markers:** {preserved / n/a (new file)}

**Ready to write changes?**"

### 8. Present MENU OPTIONS

**If dry-run mode:**

"**[DRY RUN] No files will be written. Preview above shows what would change.**

**[DRY RUN] Export manifest would be updated for {skill-name-list}: ides: {ides_written}.**

**Proceeding to token report...**"

List every skill in `skill_batch`, and give `{ides_written}` as §9b defines it, over the targets above, or `none` when it is empty. §9 to §9c do not run: delete the `{export_stage_dir}` folder, then auto-proceed to {nextStepFile}.

**If NOT dry-run:**

Display: "**Select:** [C] Continue: write changes to {context_file} | [X] Cancel and exit (or type `cancel` / `exit` / `:q`)"

**Multi-target behavior:** When processing multiple context files, present all previews together before asking for a single confirmation. After confirmation, write all target files sequentially, verifying each one.

"**Targets:** {list each context_file with its case}
**Ready to write changes to all targets?**"

Display: "**Select:** [C] Continue — write changes to all targets | [X] Cancel and exit"

#### Gate handling

- **[C]**: write the targets (§9), record the export (§9b) and write the snippets (§9c), then load, read entirely, and execute `{nextStepFile}`.
- **[X]** / `cancel` / `exit` / `:q`: delete the `{export_stage_dir}` folder, display "Cancelled: no context files were written." and HALT (exit code 6, `halt_reason: "user-cancelled"`, phase `update-context §8`).
- **Any other input** — help the user respond, then redisplay this gate.
- **Dry-run**: auto-proceed without writing.
- **GATE [default: C]**: headless, record the decision in the run sink with the command below, log "headless: auto-approve context file update", then auto-approve with [C]. If `record` exits non-zero, display its error line and go on: a failed `record` never stops the run.

```bash
uv run {emitEnvelopeHelper} record --workflow skf-export-skill --run-dir "{run_dir}" --decision <<'SKF_JSON'
{"gate":"update-context.write-confirmation","default_action":"C","taken_action":"C","reason":"headless: auto-approve context file update"}
SKF_JSON
```

### 9. Write and Verify (Non-Dry-Run Only)

For each target, in order, feed the body §4b staged at `{content_file}` to the write its §5 case picked, by stdin redirection. Never pass a body inline as `--content "…"` or through `echo`: snippets carry backticks, `$` and quotes, which the shell expands, and the helper checks the text it received, so it would report success on corrupted bytes.

**Create and Append:**

```bash
python3 {rebuildManagedSectionsHelper} "{context_path}" insert < "{content_file}"
```

**Regenerate:**

```bash
python3 {rebuildManagedSectionsHelper} "{context_path}" replace < "{content_file}"
```

Both write the `<!-- SKF:BEGIN updated:{date} -->` and `<!-- SKF:END -->` markers around the body themselves (the date from the clock), write the file atomically (temp file + rename) and read it back to check the markers and the bytes outside them. They refuse (exit 1) a body that holds a marker of its own, and a file whose markers became malformed after §5, and leave that file unchanged. They print their result as JSON on stdout and exit 0 only when `status` is `"ok"`.

On a non-zero exit, bind `{context_error}` ← `error` (the helper's stderr when stdout holds no JSON, such as a Python traceback), HALT (exit code 4, `halt_reason: "context-rebuild-failed"`, phase `update-context §9`) and report `{context_file}: {context_error}`. The targets already written stay written.

On success per file, report "**{context_file} updated successfully.** Verified by `{rebuildManagedSectionsHelper}`." and add it to `context_files_updated`.

### 9b. Update Export Manifest

**This section runs once, after every target is written** (§1 sends a run with passive context off straight here; a dry run runs no `set`, as the dry-run paragraph below says). It records each skill in `skill_batch` at the version in its `{resolved_skill_package}/metadata.json`.

**`ides_written`** is the list of IDE identifiers from `config.yaml` `ides` (e.g. `claude-code`, `cursor`, `github-copilot`) whose context file §9 wrote: the `ides` of each `target_context_files` entry §9 wrote, joined, deduplicated and sorted. It is never a context file name (`CLAUDE.md`) or a skill root (`.claude/skills/`). A file §3b rewrote adds no IDE, and with passive context off `ides_written` is empty.

For each skill, run `set`, with `--ides` only when `ides_written` is not empty:

```bash
python3 {manifestOpsHelper} {skills_output_folder} set {skill-name} {version} [--ides {ides_written}]
```

`{ides_written}` is comma-joined. `set` does the whole update, migrating a v1 manifest first, and writes the manifest atomically (the v2 shape is in `references/manifest-rebuild.md`). It exits 0 with `status: "ok"` only once the manifest is written, so that result confirms the write. Once every `set` has exited 0, bind `{manifest_path}` ← `{skills_output_folder}/.export-manifest.json`, which step 6 reports; it stays null on a dry run and after a failed write.

**Dry-run mode:** Do NOT update the manifest. Display: "**[DRY RUN] Export manifest would be updated for {skill-name-list}: ides: {ides_written}.**" (list every skill in `skill_batch`; `ides_written` is empty with passive context off, so show `none`). A dry run with passive context on displayed this line at §8 and never reaches this section. Then auto-proceed to {nextStepFile}.

**Error handling:** If `set` exits non-zero, HALT (exit code 4, `halt_reason: "manifest-write-failed"`, phase `update-context §9b`) with the helper's `error` (its stderr when stdout holds no JSON). The context files §9 wrote stay written, and no snippet is written: re-run `[EX] Export Skill` on the batch, which writes the same sections again, records the manifest and writes the snippets.

### 9c. Write the Snippets

**This section runs last, after §9b, and only when step 3 staged the snippets**: a run with passive context off has none, and a dry run never reaches it.

For each skill in `skill_batch`, copy its measured draft into its package, byte for byte, so the count step 3 measured is the count of the written file:

```bash
cp "{export_stage_dir}/drafts/{skill-name}/context-snippet.md" "{resolved_skill_package}/context-snippet.md"
```

Report "**{skill-name}: context-snippet.md written** to `{resolved_skill_package}/context-snippet.md`." and add the file to `snippets_written`, which step 6 lists in the result contract.

On a failed copy, HALT (exit code 4, `halt_reason: "write-failed"`, phase `update-context §9c`) and report `{skill-name}: context-snippet.md was not written: {error}`. The context files, the export manifest and the snippets copied before it stay written: re-run `[EX] Export Skill` on the skills whose snippet was not written (this one and the ones after it).

Once every snippet is written, delete the `{export_stage_dir}` folder.
