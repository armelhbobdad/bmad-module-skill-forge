# Exit Codes

Every hard halt in this workflow exits with a stable code so headless automators can branch on the failure class without grepping message text. Each code pairs with a `halt_reason` string carried in the headless result envelope.

| Code | Meaning              | Raised by                                                                                    |
| ---- | -------------------- | -------------------------------------------------------------------------------------------- |
| 0    | success              | step 7 (terminal)                                                                           |
| 2    | input-missing / input-invalid | step 1 §1 (headless missing `architecture-doc` arg, or invalid path) → `input-missing`; non-existent file → `input-invalid` |
| 3    | resolution-failure   | step 1 §2 (`{skills_output_folder}` does not exist or is empty → `skills-folder-missing`); step 1 §3 (forge_data_folder unconfigured → `forge-folder-unconfigured`); any stage that cannot resolve a required helper from its probe order (atomic-write, schema ref, validate-feasibility-report, enumerate-stack-skills, find-cycles), or cannot start a helper it runs → `resolution-failure` |
| 4    | write-failure        | On-Activation §5 pre-flight write probe; step 1 §4 (atomic write of report skeleton failed); step 6 §4b (result-contract write failed) |
| 5    | state-conflict       | step 1 §3 (fewer than 2 valid skills found: a stack requires ≥2 → `insufficient-skills`); step 1 §1 (in headless, `--previous-report` is `{outputFile}` or `{outputFileLatest}`, a file this run overwrites → `previous-report-collision`; an interactive run asks for another path); step 6 §1 (the report fails the feasibility-report check → `schema-violation`) |
| 6    | user-cancelled       | step 1 §1 prompt cancelled; any prompt that accepted `cancel`/`exit`/`:q` |
| 7    | inventory-unreliable | step 1 §2 (enumerate-stack-skills warnings exceed its failure budget); step 3 §3 (>20% API-surface subagents return malformed JSON); skills SKF did not generate are not counted |
