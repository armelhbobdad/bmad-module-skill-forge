<!-- Config: communicate in {communication_language}. -->

# HARD HALT Contract

The exit-code map, the envelope every HARD HALT emits, the headless progress events and the `--batch` rule.

## Exit Codes

Every HARD HALT in this workflow exits with a stable, documented code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning             |
| ---- | ------------------- |
| 0    | success             |
| 2    | input-invalid       |
| 3    | resolution-failure  |
| 4    | write-failure       |
| 5    | overwrite-cancelled |
| 6    | user-cancelled      |
| 7    | finalize-blocked    |
| 8    | ecosystem-redirect  |
| 9    | state-conflict      |

Exit 8 (`ecosystem-redirect`) is reserved, as is the `ecosystem-check.ecosystem-match` gate: step 2 raises neither until agentskills.io has a registry API.

## Result Contract on HARD HALT

Every HARD HALT emits an **error envelope** through the shared emitter, `{emitEnvelopeHelper}`, so no HARD HALT leaves a headless automator without a result line, except SKILL.md On Activation's halt for a missing `python3` or `uv`, which the emitter needs: that halt displays its message alone. SKILL.md On Activation step 1 resolved the emitter; when a compaction lost it, it is the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. Stage the halt payload as `{run_dir}/halt.json` through a quoted heredoc, then run the emitter:

```bash
cat > "{run_dir}/halt.json" <<'SKF_JSON'
{"phase": "<step slug>", "halt_reason": "<code>", "reason": "<the halt message, one line>", "skill_package": null}
SKF_JSON
uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

- `phase`: the step's slug (`resolve-target`, `ecosystem-check`, `quick-extract`, `compile`, `write-and-validate`, `finalize`), `on-activation` for a halt before the run starts (SKILL.md On Activation, and batch mode's refusal of `--description` and `--exports` and of the hint flags), or `batch-mode` for batch mode §1 to §4.
- `halt_reason`: the failure class the halt names: the Meaning of its exit code in the table above, or `not-skf-output` or `flat-layout` for exit 9. The emitter derives `exit_code` from it.
- `reason`: the message the step displayed, as one line (its first sentence when it runs longer); it becomes `error.message`. Escape `"` and `\` in it as JSON requires.
- `skill_package`: the absolute `{skill_package}` once step 5 §1 computed it, else `null`.
- `outputs` (optional): the files already on disk, as `{"skill_md": ..., "context_snippet": ..., "metadata": ...}` paths.
- `details` (only when the halt names them): the halt's context as an object, such as the folder a refusal names or the file a failed write named. The emitter puts it in the envelope's `error.details`, beside the `code` and `message` it builds from `halt_reason` and `reason`, so no halt types an `error` object.

The emitter prints one line on stderr, `SKF_QUICK_SKILL_RESULT_JSON: {...}`: display it verbatim. If it exits non-zero, fix `halt.json` once (its `message` names the problem) and run it again; if it still fails, or no path resolved for `{emitEnvelopeHelper}`, display the halt message alone.

**Additionally, when `{skill_package}/metadata.json` exists** (HALT at step 5 §1 onward, except the step 5 §1 ownership halt, which writes nothing on disk: `{skill_package}` would sit in a folder SKF did not generate), the command adds `--result-dir "{skill_package}"`, and the emitter also writes the envelope (without the `SKF_QUICK_SKILL_RESULT_JSON: ` prefix) to disk:

```
{skill_package}/quick-skill-result-{YYYYMMDD-HHmmss}.json
{skill_package}/quick-skill-result-latest.json   (copy, not symlink)
```

so the halt's record also becomes the `-latest.json` copy; a caller still reads the run's own `SKF_QUICK_SKILL_RESULT_JSON` line, never the copy in its place. Before step 5 §1 computes `{skill_package}`, the stderr line and the exit code are the whole contract. A HALT while `{skill_package}` has no `metadata.json` (a failed first write in step 5 §2, for example) writes nothing on disk either: a package holding only result files is not SKF output, so the next run's ownership check would refuse it.

**Schema:** `shared/scripts/schemas/skf-quick-skill-result-envelope.v1.json` (installed under `{project-root}/_bmad/skf/`).

## Headless Events

When `{headless_mode}` is true, each step prints one-line JSON progress events on stderr (one line each, never pretty-printed), so a pipeline can follow a run live:

- when the step starts: `{"step":N,"name":"<slug>","status":"start"}`
- just before it chains to its `nextStepFile`: `{"step":N,"name":"<slug>","status":"done"}`
- at a HARD HALT, in place of `done`: `{"step":N,"name":"<slug>","status":"halt","exit":<code>}`

`N` and `<slug>`: 1 `resolve-target`, 2 `ecosystem-check`, 3 `quick-extract`, 4 `compile`, 5 `write-and-validate`, 6 `finalize`, 7 `health-check`. A `--batch` run adds the per-target events `skf-quick-batch.py` prints (`references/batch-mode.md` §2 to §4).

## In `--batch`

A HARD HALT in steps 1 to 6 ends the current target, not the batch. After its envelope line and `halt` event, return to `references/batch-mode.md` §3, which records the target and prints its `fail` event: control returns there even when the halt message reads as the end of the run, so a target's halt never exits the process. The batch then takes its next target, or, under `--fail-fast`, writes its summary. A halt before the first target (SKILL.md On Activation, batch mode's refusal of `--description` and `--exports`, or batch mode §1) ends the run itself, with no batch summary. A batch mode §2 to §4 halt ends the run too and writes no batch summary, though a `batch_summary` event an earlier `summarize` already printed stays the batch's result; the targets recorded before it keep the `done` and `fail` events they printed.
