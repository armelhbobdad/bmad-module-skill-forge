<!-- Config: emit exactly as specified — this is a machine-parsed contract. Loaded standalone by any halting stage; it back-references no other file. -->

# Headless Result Envelope

The single-line JSON envelope export-skill emits on non-interactive (`{headless_mode}`) runs. Pipeline consumers parse it to branch on the run's outcome, so its shape must be reproduced exactly. This file stands alone — every HARD-HALT stage can load it without SKILL.md in context.

## Emission rule

- **Success / dry-run:** step 6 (`summary.md`) emits the envelope on **stdout**, once, before chaining to step 7.
- **Every HARD HALT:** emit the same envelope shape on **stderr** with `status: "error"`, then exit with the matching code.

## Shape

```
SKF_EXPORT_RESULT_JSON: {"status":"success|error|dry-run","skills":[],"context_files_updated":[],"manifest_path":"…|null","headless_decisions":[],"exit_code":0,"halt_reason":null}
```

## Fields

- `status` — `"success"` on the terminal happy path, `"dry-run"` when `--dry-run` skipped the §4 context and manifest writes (the run still reaches the terminal step), `"error"` on any HALT.
- `skills` — resolved skill names in the batch (JSON array).
- `context_files_updated` — context files successfully written this run (JSON array; `[]` when a HALT preceded any write).
- `manifest_path` — the written manifest path, or `null` when no manifest write completed.
- `headless_decisions` — the `{gate, default_action, taken_action, reason}` entries logged as each gate auto-resolved (JSON array).
- `exit_code` — 0 success/dry-run · 2 input-missing · 3 resolution-failure · 4 write-failure · 5 state-conflict · 6 user-cancelled.
- `halt_reason` — `null` on success/dry-run, else one of: `"input-missing"`, `"resolution-failure"`, `"malformed-markers"`, `"manifest-write-failed"`, `"context-rebuild-failed"`, `"write-failed"`, `"user-cancelled"`. Each value is emitted by a real HALT site (see the SKILL.md Exit Codes table for the code↔reason map); the enum lists no value that no stage emits.

A halting stage sets the branch-specific fields inline (e.g. `manifest_path: null`, `context_files_updated: []`) and fills the rest from the shape above.
