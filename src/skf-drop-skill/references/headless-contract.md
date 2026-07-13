# Headless Result Envelope

The single-line JSON contract every headless run of skf-drop-skill emits. It stands alone: the stages that emit it load this file directly, so an error path never depends on any other file staying in context under compaction.

When `{headless_mode}` is true, step 3 emits this envelope on **stdout** before chaining to step 4; every HARD HALT emits the same shape on **stderr** with `status: "error"`:

```
SKF_DROP_SKILL_RESULT_JSON: {"status":"success|error|dry-run","skill":"…|null","drop_mode":"…|null","versions_affected":[],"files_deleted":[],"manifest_updated":false,"exit_code":0,"halt_reason":null}
```

Field rules:

- `status` — `"success"` on the terminal happy path, `"dry-run"` when `--dry-run` was set and the workflow exited at the confirmation gate before any mutation, `"error"` on any HALT.
- `halt_reason` — `null` on success/dry-run; otherwise one of `"input-missing"`, `"input-invalid"`, `"manifest-corrupt"`, `"nothing-to-drop"`, `"active-version-guard-refused"`, `"headless-purge-forbidden"`, `"manifest-write-failed"`, `"context-rebuild-failed"`, `"delete-failed"`, `"write-failed"`, `"user-cancelled"`.
- `exit_code` — the stable numeric code the emitting HALT specifies (`0` on success/dry-run).
- `skill` / `drop_mode` / `versions_affected` / `files_deleted` / `manifest_updated` — the discriminating values the emit site supplies; any key not yet resolved at that point takes the default shown in the template (`null`, `[]`, or `false`).

Each emit site supplies its own `exit_code`, `halt_reason`, and whichever discriminating fields are known at that point; all other keys default as shown.
