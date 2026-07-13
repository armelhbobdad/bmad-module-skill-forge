# Exit Codes — skf-rename-skill

Every HARD HALT in the rename workflow exits with a stable code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 4 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §4/§5 (headless missing `old_name`/`new_name` arg) → `input-missing`; new name fails kebab-case / length / same-as-old → `input-invalid` |
| 3    | resolution-failure   | step 1 §2 (manifest is malformed JSON); step 1 §3 (no skills found anywhere)               |
| 4    | write-failure        | On-Activation §4 pre-flight write probe (skills_output_folder / forge_data_folder unwritable); step 2 §1 (copy → `copy-failed`); step 2 §2 (inner-dir rename) / §3 (file content update) / §4 (symlink repair) → `write-failed`; step 2 §6 (manifest write → `manifest-write-failed`). step 2 §7 (context-file rewrite) is **best-effort and never halts** — per-file failures are recorded in `context_files_failed` and the rename still succeeds (manifest + disk are canonical; re-run `[EX] Export Skill` to retry). |
| 5    | state-conflict       | step 1 §5 (name-collision check fails: target name already in use); step 1 §6 (source-authority="official" headless without `force_source_authority_in_headless`); concurrency lock collision (`halted-for-concurrent-run`); step 2 §5 (no-trace verification failed — `{old_name}` still present inside the new location → `verify-failed`; note this rollback is code 5, unlike the copy/write rollbacks at code 4) |
| 6    | user-cancelled       | step 1 §6 (source-authority warning [N]); step 1 §8 confirmation gate `[N]`; any prompt that accepted `cancel`/`exit`/`:q` |
