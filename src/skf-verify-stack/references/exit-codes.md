# Exit Codes

Every hard halt in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text. Each code pairs with a `halt_reason` string carried in the headless result envelope.

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §1 (headless missing `architecture-doc` arg, or invalid path) → `input-missing`; non-existent file → `input-invalid` |
| 3    | resolution-failure   | step 1 §2 (`{skills_output_folder}` does not exist or is empty → `skills-folder-missing`); step 1 §3 (forge_data_folder unconfigured → `forge-folder-unconfigured`); any stage that cannot resolve a required shared helper (atomic-write, schema ref, validate-feasibility-report) from its probe order → `resolution-failure` |
| 4    | write-failure        | On-Activation §5 pre-flight write probe; step 1 §4 (atomic write of report skeleton failed); step 6 §4b (result-contract write failed) |
| 5    | state-conflict       | step 1 §3 (fewer than 2 valid skills found — stack requires ≥2 → `insufficient-skills`); step 1 §1 (`previousReport` resolves to same inode as `{outputFile}` → `previous-report-collision`); step 6 §1 (report section order or schemaVersion mismatch → `schema-violation`) |
| 6    | user-cancelled       | step 1 §1 prompt cancelled; any prompt that accepted `cancel`/`exit`/`:q`; step 6 menu cancelled |
| 7    | inventory-unreliable | step 1 §2 (>20% subagent failures or enumerate-stack-skills warnings exceed budget); step 3 §3 (>20% API-surface subagents return malformed JSON) |
| 8    | analysis-halted      | coverage.md §7 & integrations.md §7 — user picks [X] at an elective vacuous-analysis gate. These gates are interactive-only; in headless they auto-continue, so exit 8 never fires headlessly and `analysis-halted` never appears in the result envelope. |
