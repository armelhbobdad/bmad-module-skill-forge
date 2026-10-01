<!-- Config: communicate in {communication_language}. -->

# HARD HALT Contract

The exit-code map, the envelope every HARD HALT emits, the headless progress events and the `--batch` rule. Each HARD HALT in the stage files names its phase, `halt_reason`, exit code and emit command, and each stage's Rules carry its `halt` event and the `--batch` return, so a halt keeps its wire format even when SKILL.md or this file was compacted away.

## Exit Codes

Every HARD HALT in this workflow exits with a stable, documented code so headless automators can branch on the failure class without grepping message text:

| Code | Meaning                | Raised by                                                   |
| ---- | ---------------------- | ----------------------------------------------------------- |
| 0    | success                | step 7 (terminal)                                          |
| 2    | input-invalid          | batch mode, before any target runs (`--description`, `--exports`, `--language-hint` or `--scope-hint` passed with `--batch`; §1: a batch file it cannot read, or `skf-quick-batch.py` missing); step 1 §1 (a headless run with no target) |
| 3    | resolution-failure     | step 1 (a target that is no GitHub repository or package §2, registry chain §3, version tag missing or not checkable §3a, file listing unreadable, language abort or no language found §4); step 3 (non-library shape §1.5, zero-exports §4.5) |
| 4    | write-failure          | SKILL.md On Activation step 1 (the run folder cannot be created); batch mode §1 (the batch run folder cannot be written); step 5 §2 (deliverable write failed) |
| 5    | overwrite-cancelled    | step 5 §1 (user selected [N])                              |
| 6    | user-cancelled         | step 1 §1 ([X] Cancel and exit, or cancel-line affordance) and §3 ([X] at the ambiguous-name gate); step 2 §3 ([A] Abort at ecosystem-match gate); step 4 §6 (user selected [Q]) |
| 7    | finalize-blocked       | step 6 §1 (active-pointer flip refused — non-link in place) |
| 8    | ecosystem-redirect     | step 2 §3 ([I] Install at ecosystem-match gate — user opted to install the existing official skill instead of compiling a custom community skill) |
| 9    | state-conflict         | step 5 §1 (ownership check: the skill folder or the version folder it writes is not SKF output, or SKF cannot check it → error.code `not-skf-output`; an SKF skill still in the flat layout → `flat-layout`) |

## Result Contract on HARD HALT

Every HARD HALT emits an **error envelope** through the shared emitter, `{emitEnvelopeHelper}`, so headless automators never meet a failed run with no result. SKILL.md On Activation step 1 resolved it; when a compaction lost it, it is the first existing path of `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py` and `{project-root}/src/shared/scripts/skf-emit-result-envelope.py`. Stage the halt payload as `{run_dir}/halt.json` through a quoted heredoc, then run the emitter:

```bash
cat > "{run_dir}/halt.json" <<'SKF_JSON'
{"phase": "<step slug>", "halt_reason": "<code>", "reason": "<the halt message, one line>", "skill_package": null}
SKF_JSON
uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"
```

- `phase`: the step's slug (`resolve-target`, `ecosystem-check`, `quick-extract`, `compile`, `write-and-validate`, `finalize`), `on-activation` for a halt before the run starts (SKILL.md On Activation, and batch mode's refusal of `--description` and `--exports` and of the hint flags), or `batch-mode` for batch mode §1.
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

so consumers that hardcode the `-latest.json` path see a deterministic file even on failed runs. Before step 5 §1 computes `{skill_package}`, the stderr line and the exit code are the whole contract. A HALT while `{skill_package}` has no `metadata.json` (a failed first write in step 5 §2, for example) writes nothing on disk either: a package holding only result files is not SKF output, so the next run's ownership check would refuse it.

**Schema:** `shared/scripts/schemas/skf-quick-skill-result-envelope.v1.json` (installed under `{project-root}/_bmad/skf/`).

## Headless Events

When `{headless_mode}` is true, each step prints one-line JSON progress events on stderr (one line each, never pretty-printed), so a pipeline can follow a run live:

- when the step starts: `{"step":N,"name":"<slug>","status":"start"}`
- just before it chains to its `nextStepFile`: `{"step":N,"name":"<slug>","status":"done"}`
- at a HARD HALT, in place of `done`: `{"step":N,"name":"<slug>","status":"halt","exit":<code>}`

`N` and `<slug>`: 1 `resolve-target`, 2 `ecosystem-check`, 3 `quick-extract`, 4 `compile`, 5 `write-and-validate`, 6 `finalize`, 7 `health-check`. A `--batch` run adds the per-target events of `references/batch-mode.md`.

## In `--batch`

A HARD HALT in steps 1 to 6 ends the current target, not the batch. After its envelope line and `halt` event, return to `references/batch-mode.md` §3, which records the target and prints its `fail` event: control returns there even when the halt message reads as the end of the run, so a target's halt never exits the process. The batch then takes its next target, or, under `--fail-fast`, writes its summary. A halt before the first target (SKILL.md On Activation, batch mode's refusal of `--description` and `--exports`, or batch mode §1) ends the run itself, with no batch summary.
