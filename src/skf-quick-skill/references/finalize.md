---
nextStepFile: 'health-check.md'
atomicWriteProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py'
  - '{project-root}/src/shared/scripts/skf-atomic-write.py'
---

<!-- Config: communicate in {communication_language}. Generated SKILL.md text in {document_output_language}. -->

# Step 6: Finalize

## STEP GOAL:

To finalize the skill by creating the active-version pointer, displaying the completion summary, and emitting the result envelope and result contract.

## Rules

- Do not rewrite deliverables — they were written and validated in step 5
- Emit the result envelope and contract through the shared emitter, never by hand; when it is missing or fails twice, say the contract was not written and go on (§3)
- A HARD HALT prints, after its envelope, this step's `halt` event when `{headless_mode}` is true. Under `--batch` it ends only this target: then return to `references/batch-mode.md` §3, even when the halt reads as the end of the run (`references/halt-contract.md`).

## Steps

### 1. Create Active Pointer (atomic flip, Windows-safe)

**If `{overrides.no_active_pointer}` is true**, skip the helper invocation entirely. Log: "Active pointer: skipped per `--no-active-pointer` override." Do not update `{skill_group}/active`, and set `{active_pointer}` to `skipped-no-active-pointer`. Proceed to §2 with the active-pointer line omitted from the completion summary and the outputs payload.

`{skill_group}` and `{skill_package}` were computed in step 5 §1 from `{skills_output_folder}`, `{repo_name}`, and `{version}`; `{version}` is the `version` of the `metadata.json` step 5 installed.

Point `{skill_group}/active` at `{version}` with the shared helper.

**Resolve `{atomicWriteHelper}`** from `{atomicWriteProbeOrder}`; first existing path wins. If no candidate exists, skip the flip the same way `--no-active-pointer` does: log "Active pointer: skipped, atomic-write helper unavailable", omit the active-pointer line from the completion summary and outputs, and set `{active_pointer}` to `skipped-helper-missing`, which the result-contract summary (§3) carries so consumers see why the pointer is absent. This branch is reached only when `skf-atomic-write.py` disappeared after step 5, whose metadata.json install halts without it. There is no manual fallback: a hand-rolled `rm` + `ln -s` loses the helper's atomicity and non-link guard, risking a half-flipped pointer or an `rm -rf` into a real directory.

```bash
uv run {atomicWriteHelper} flip-link \
  --link "{skill_group}/active" \
  --target "{version}"
```

On exit 0 the helper prints `{"link": …, "points_to": …, "kind": …, "status": "ok"}` on stdout. On any other exit, HARD HALT the workflow with **exit code 7 (finalize-blocked)**: "Refusing to flip `{skill_group}/active`: {the `message` of the helper's `{"status": "error", "message": …}` stderr line (something that is not a link is at `{skill_group}/active`, or another process holds its lock), else its stderr}." Stage `{"phase": "finalize", "halt_reason": "finalize-blocked", "reason": "Refusing to flip {skill_group}/active: <the helper's message>", "skill_package": "{skill_package}", "outputs": {"skill_md": "{skill_package}/SKILL.md", "context_snippet": "{skill_package}/context-snippet.md", "metadata": "{skill_package}/metadata.json"}}` as `{run_dir}/halt.json` (`context_snippet` left out under `--skip-snippet`) and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" --target stderr < "{run_dir}/halt.json"` (`references/halt-contract.md`). When a real folder is at `{skill_group}/active`, a common cause on Windows is a prior run that executed `ln -s` under git-bash without Developer Mode enabled, which silently wrote a full directory copy: remove that copy and retry.

Confirm: "Active pointer: {skill_group}/active -> {version} ({kind})" where `{kind}` is `symlink` or `junction` as returned by the helper, and set `{active_pointer}` to that `{kind}`.

### 2. Display Completion Summary

"**Quick Skill complete.**

**Skill:** {repo_name} v{version}
**Language:** {language}
**Source:** {resolved_url}
**Authority:** community
**Confidence:** {extraction confidence}
{If `scope_hint` is non-empty, add:} **Scope:** {scope_hint}
{If step 3 recorded a `repo_shape`, add:} **Repo shape:** {repo_shape}
{If it is `skills-module`, add:} **Skills:** {skill count} skills and {menu code count} menu codes, documented as the exports below

**Files written:**
- `{skill_package}/SKILL.md`
- `{skill_package}/context-snippet.md` (omit this line when `--skip-snippet` was set)
- `{skill_package}/metadata.json`
- `{skill_group}/active` -> `{version}` (omit this line when `--no-active-pointer` was set)

{If step 5 §1 set `{replaced_build}`, add:} **Replaced:** the `{replaced_build}` build of v{version}. Its forge data, `{forge_data_folder}/{repo_name}/{version}/`, is left in place: remove it yourself once you no longer need it.

**Exports documented:** {count}
**Validation:** {pass / N issues (advisory)}

---

**Recommended next steps:**

1. **test-skill** (advisory) — Run cognitive completeness verification on the generated skill
2. **export-skill** — Package and distribute the skill with platform-aware context injection

**Note:** This is a best-effort community skill. For deeper analysis with AST-verified exports and provenance tracking, use the full **create-skill** workflow with a skill brief."

### 3. Result Envelope and Result Contract

Stage the run's result payload through a quoted heredoc, then run the shared emitter, which prints the success envelope and writes the result contract:

```bash
cat > "{run_dir}/result-context.json" <<'SKF_JSON'
{
  "status": "success",
  "skill_package": "{skill_package}",
  "outputs": {"skill_md": "{skill_package}/SKILL.md", "context_snippet": "{skill_package}/context-snippet.md", "metadata": "{skill_package}/metadata.json", "active_pointer": "{skill_group}/active"},
  "summary": {
    "skill_name": "{repo_name}",
    "version": "{version}",
    "language": "{language}",
    "exports_documented": {export count},
    "quality_score": {quality_score},
    "confidence": "{extraction confidence}",
    "repo_shape": {repo_shape},
    "language_resolution": {language_resolution},
    "detected_languages": {detected_languages},
    "zero_exports_rescue": {zero_exports_rescue},
    "active_pointer": "{active_pointer}",
    "validation_issues": {validation_issues}
  },
  "result_contract": {
    "skill": "skf-quick-skill",
    "outputs": [
      {"type": "skill", "path": "{skill_package}/SKILL.md"},
      {"type": "skill", "path": "{skill_package}/context-snippet.md"},
      {"type": "skill", "path": "{skill_package}/metadata.json"}
    ]
  }
}
SKF_JSON
uv run {emitEnvelopeHelper} emit --workflow skf-quick-skill --run-dir "{run_dir}" --result-dir "{skill_package}" < "{run_dir}/result-context.json"
```

This list is the summary, once: `skill_name`, `version`, `language`, `exports_documented` (the export count), `quality_score` and `validation_issues` (step 5, the object `{"skill_md": <n>, "context_snippet": <n>, "metadata": <n>, "security": <n>}`), `confidence` and `repo_shape` (step 3, the shape null when it recorded none), `language_resolution` and `detected_languages` (step 1), `zero_exports_rescue` (step 3 §4.5, else null) and `active_pointer` (§1). Write each value as JSON: a string in double quotes with any `"` or `\` escaped, every path absolute with `/`, and `null` for a value the run did not record. Leave the snippet out of both `outputs` under `--skip-snippet`, and `outputs.active_pointer` out when §1 flipped no pointer.

The emitter writes the result contract from `result_contract`, with the payload's own `status` and `summary`, so neither is typed twice (the per-run record `{skill_package}/quick-skill-result-{YYYYMMDD-HHmmss}.json` and its copy `quick-skill-result-latest.json`, the stable path for pipeline consumers) and prints one line on stdout, `SKF_QUICK_SKILL_RESULT_JSON: {...}`. In a headless single-target run, bind `{result_envelope_line}` ← that line and do not display it here: the shared health check displays it verbatim as the run's last line, so a `claude -p` caller reads the envelope as the final message. Otherwise (an interactive run, or a `--batch` target) display it verbatim as its own line. If it exits non-zero, fix `result-context.json` once (its `message` names the problem) and run it again; if it still fails, or no path resolved for `{emitEnvelopeHelper}`, leave `{result_envelope_line}` empty, say that the result contract was not written and why, and go on.

**Post-completion hook (optional).** If `{onCompleteCommand}` is non-empty (resolved at SKILL.md On Activation §3 from `workflow.on_complete`) and the emitter wrote the result contract (the line it printed has a non-null `result_path` and no `result_file_write_failed` warning naming `quick-skill-result-latest.json`), invoke it after the result contract is finalized:

```bash
{onCompleteCommand} --result-path={skill_package}/quick-skill-result-latest.json
```

When the emitter failed twice, no path resolved for `{emitEnvelopeHelper}`, `result_path` is null, or a `result_file_write_failed` warning names `quick-skill-result-latest.json` (the copy alone failed), skip the hook and say so: "Post-completion hook skipped: `quick-skill-result-latest.json` was not written." The hook never gets a missing file or an earlier run's `-latest` copy. Log success/failure but never fail the workflow on a hook error: the skill is already written. The hook runs last so a git-add, registry registration, or notifier sees a complete package. Under `--batch` it runs once per target that reaches this section.

In a single-target run, then delete the run folder, which a finished run no longer needs: the files step 3 fetched into it, and the files the steps staged (if `rmdir` reports it is not empty, leave it). The `case` guard deletes nothing unless the path is a quick-skill run folder:

```bash
case "{run_dir}" in */.skf-run/skf-quick-skill-*) rm -rf "{run_dir}/src" && rm -f "{run_dir}"/*.json "{run_dir}"/*.jsonl "{run_dir}"/*.txt && rmdir "{run_dir}" ;; esac
```

Under `--batch`, leave it: batch mode §3 records the target from it, then removes it.

### 4. Chain to Health Check

**Single target.** Once the active pointer, completion summary, result envelope, any post-completion hook and the run folder's removal are done, print this step's `done` event and step 7's `start` event when `{headless_mode}` is true (`references/halt-contract.md`), then load and execute {nextStepFile}. Do not stop here: health-check is the true terminal step even though the summary reads as final.

**Under `--batch`.** Print this step's `done` event, then return to `references/batch-mode.md` §3 instead of {nextStepFile}: control returns there even though this step reads as the end of the run. The health check runs once, after the batch summary.
