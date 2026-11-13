---
nextStepFile: 'step-06-batch.md'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
decisionLogFile: '{campaignWorkspacePath}/_campaign-decision-log.md'
preapplyLogFile: '{campaignWorkspacePath}/preapply-log.json'
depsScript: 'scripts/campaign-deps.py'
kickoffTemplate: '{kickoffTemplatePath}'
kickoffScript: 'scripts/campaign-render-kickoff.py'
gateScript: 'scripts/campaign-quality-gate.py'
stateScript: 'scripts/campaign-state.py'
validateScript: 'scripts/campaign-validate-state.py'
# The customization helper the kickoff pipe runs (§5).
resolveCustomizationProbeOrder:
  - '{project-root}/_bmad/skf/shared/scripts/skf-resolve-customization.py'
  - '{project-root}/src/shared/scripts/skf-resolve-customization.py'
---

<!-- Config: communicate in {communication_language}. -->

# Skill Loop

## STEP GOAL:

Iterate skills in `dependency_graph.execution_order`, processing each Tier A skill through the full pipeline while enforcing dependency gates. Write state after each skill completes to survive context death between skills.

## RULES

- Write `campaign.current_stage` = 4 only in this stage's final state write (§6), after every skill: step-resume resumes at `current_stage + 1`, so an early write skips unfinished work. An interrupted skill needs no stage write: it stays `active`, and resume sends an active Tier A skill back to this stage.
- Write state and decision-log entries only through `{stateScript}`, and on a non-zero exit HALT with the same code (State Contract in `references/campaign-contracts.md`). A log entry is `uv run {stateScript} log --log-file {decisionLogFile} --type <decision|auto|event> --text '<entry>'`.
- A `--halt-reason` text is single-quoted as a log entry is, an apostrophe written as `'\''` (`references/campaign-contracts.md`, Decision Log).
- Write state after EACH skill completes (not just at end): context death between skills must be survivable.
- The per-skill pipeline body (§5.2) runs inline, not in a delegated subagent: BS→CS→TS are nested skill activations, and a subagent cannot spawn further subagents, so running inline keeps the full pipeline reachable and writes each skill's state before the next begins.
- If `{headless_mode}` is true, auto-proceed through confirmation gates; at a blocked skill, headless takes §4.6's `default_action` and never forces a dependency. Emit this stage's progress events, and at any HARD HALT the error envelope, per `references/campaign-contracts.md`.
- When state sets `campaign.unattended` to true (the plan gate's `[U]nattended`, or `campaign resume --unattended`), an interactive run takes §4.6's `default_action` too, and never forces a dependency.

## TASKS

### §1: Read + Validate State

Load `{stateFile}`. Run `uv run {validateScript} --state-file {stateFile}`; on non-zero, HALT (exit 3) with the script's `errors[]`.

### §2: Read Brief

Load `{briefFile}` only to confirm it parses (the kickoff script reads it directly). HALT (exit code 8, `missing-brief`) if the brief is missing or unreadable.

### §3: Read Directive

If `campaign.directive_path` is set in state, the directive steers this stage through two scripts, so apply none of it by hand: the gate script's resolve calls read its `## Skip List` and `## Quality Overrides` for each skill (§4 and §5, re-reading the file, so an edit between skills takes effect), and the kickoff script inlines the whole file into each kickoff (§5), where its other sections are the campaign-wide context the directive contract in `references/campaign-directive-spec.md` describes. If the file is not found, continue without error (directive is optional).

### §4: Dependency Gate Check

For each skill in `dependency_graph.execution_order`, before processing:

1. Skip Tier B skills: they are processed in step-06 via batch mode.
2. Skip skills whose status is already `"completed"`, `"failed"`, or `"skipped"` (resume support).
3. Resolve the skill's run, passing `--directive-file` when state sets `campaign.directive_path`:

   ```
   uv run {gateScript} resolve --state-file {stateFile} --skill {skill_name} --brief-file {briefFile} [--directive-file <campaign.directive_path>]
   ```

   First, when its `directive_notice` is not null, log it: `uv run {stateScript} log --log-file {decisionLogFile} --type event --once --text '<directive_notice>'`. The notice describes the directive, not the skill, and `--once` appends it only when the log does not hold it yet. When `skip` is true, the directive's Skip List names the skill: mark it skipped (`uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} --status skipped --halt-reason 'directive Skip List: <skip_reason>'`, with `'directive Skip List'` when `skip_reason` is null), log "directive Skip List: {skill_name} ({skip_reason})" (type `event`), and continue to the next skill. Otherwise keep its `brief_skill`, the brief-skill inputs §5.2 copies. On exit 2, HALT with its `error`: exit code 8 (`missing-brief`) when its `code` is `BRIEF_NOT_FOUND`, `BRIEF_UNREADABLE` or `TARGET_NOT_FOUND` (the brief has no target for the skill), else exit code 2 (`invalid-input`): an override that breaks the gate, or a directive that cannot be read.
4. Run `uv run {depsScript} --check --state-file {stateFile} --skill {skill_name}`.
5. If `ready: true`, proceed to §5 for this skill.
6. If `ready: false`, present the blocked skill and each unmet dependency with its status (`unmet_status`):
   - `[S]kip`: mark the skill skipped with `uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} --status skipped --halt-reason 'unmet dependency: <dependency> is <status>'` (one such clause per unmet dependency, joined by `, `), log it, continue to the next skill.
   - `[F]orce`: re-run with `--force`, proceed to §5 despite unmet deps.
   - `[H]alt`: stop the campaign with exit code 13 (`dependency-blocked`); state is intact and resumable.

   **GATE [default: `default_action`]**: headless, take `default_action`; a run whose state sets `campaign.unattended` to true takes it too. `skip` (every unmet dependency failed or was skipped, so none can complete in this run) runs `[S]kip` and logs "<mode>: skipped {skill_name}: {dependency} is {status}" (type `auto`, `<mode>` `headless` when `{headless_mode}` is true, else `unattended`) for each unmet dependency, so the independent skills after it still run. `halt` (a dependency is still pending or active, an order the loop cannot follow) logs "<mode>: halted at {skill_name}: {dependency} is {status}" (type `auto`) for each unmet dependency, then runs `[H]alt`.
7. If the pass ends with a Tier A skill still `pending` (only a hand-edited state can do this), HALT (exit code 7, `dependency-deadlock`) and log it (type `event`).

### §5: Per-Skill Processing

For each ready Tier A skill:

1. **Activate:** `uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} --status active`. It stamps `started_at` from the clock, or keeps the start of a run an interruption left `active`.
2. **Execute pipeline:**
   - **Pre-apply:** apply known workarounds before generation by running the shared pre-apply helper against the skill's working directory:
     ```
     uv run {project-root}/_bmad/skf/shared/scripts/skf-preapply.py --target-dir <skill-working-dir> --log-dir {campaignWorkspacePath}
     ```
     (During development, with no `{project-root}/_bmad/skf/shared/scripts/skf-preapply.py` installed, the helper lives at `{project-root}/src/shared/scripts/skf-preapply.py`.) It writes its `applied[]` workarounds to `{preapplyLogFile}`, which the kickoff script reads. Pre-apply is best-effort: if the helper is missing or exits non-zero, log a warning and proceed (it is not a gate), and leave `--workarounds-file` out of the kickoff call below, so an earlier skill's log is never listed for this one.
   - **Kickoff emit:** render the whole kickoff message with the kickoff script, which fills every placeholder of the template. The customization resolver pipes the persistent facts into it:
     ```
     uv run {resolveCustomizationHelper} --skill {skill-root} --project-root {project-root} --key workflow.persistent_facts | uv run {kickoffScript} --state-file {stateFile} --brief-file {briefFile} --skill {skill_name} --template {kickoffTemplate} [--workarounds-file {preapplyLogFile}] --facts-json - --project-root {project-root} [--directive-file <campaign.directive_path>]
     ```
     - `{resolveCustomizationHelper}` is resolved from `{resolveCustomizationProbeOrder}` when it is not bound.
     - `--facts-json -` takes `workflow.persistent_facts` from the resolver unchanged, and the script drops each `!` entry and expands each glob with the resolver's own code. When the resolver is missing or fails, run the call without the pipe, with `--facts-toml {skill-root}/customize.toml` in place of `--facts-json -`: the script reads the bundled list itself, so no fact or workaround ever passes through shell quoting.
     - `--workarounds-file` is passed when pre-apply exited 0 for this skill; the script lists each workaround it applied (the file, the fingerprint and its fix, the severity).
     - `--directive-file` is passed when state sets `campaign.directive_path`.

     Present the script's output unchanged as the context for the skill's pipeline run, and fill nothing in by hand. An exit 2 with no JSON on stderr is a usage error from a mangled call, not invalid input: fix the call and run it again. An exit 2 with JSON names its `code`: on `BAD_WORKAROUNDS` or `BAD_FACTS` this call's input is wrong, so correct it and run the call again; on `BRIEF_NOT_FOUND` or `BRIEF_UNREADABLE`, HALT (exit code 8, `missing-brief`); on any other code, HALT (exit code 2, `invalid-input`) with its `error`. Correct a call once only: when the corrected call fails too, HALT (exit code 2, `invalid-input`).
   - **BS → CS → TS**: the forge pipeline for a named skill, the chain the forger's `forge` alias runs. Run each sub-skill with `--headless`, so no nested gate waits and each prints its result envelope. A sub-skill that fails ends the pipeline, and the skill fails (§5.3) with its `halt_reason`. Campaign runs no analyze-source pass: brief-skill scopes the named skill itself, while analyze-source names its briefs from the repository, so brief-skill would overwrite or never read them.
     - **BS** (`skf-brief-skill`): `--headless --force` with each non-null field of §4's `brief_skill` as the input of that name (`target_repo`, `skill_name`, `target_version`, `language_hint`, `scope_hint`); copy them, never read them out of the kickoff. `--force` replaces a brief an earlier attempt wrote under this name. Record the `brief_path` of its SKF_BRIEF_RESULT_JSON at once, so resume and the report have it: `uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} --brief-path <brief_path>`. An envelope with `status` `error` fails the skill with its `halt_reason`; a BS run that printed none fails it with halt reason `no-result`, logged as "no SKF_BRIEF_RESULT_JSON line".
     - **CS** (`skf-create-skill`): `--headless` with that `brief_path`. CS prints one SKF_CREATE_SKILL_RESULT_JSON line: on stdout when it finishes the brief, on stderr when it halts. A `failed` line fails the skill with its `summary.halt_reason`. A CS run that printed no line fails the skill too, with halt reason `no-result`, logged as "no SKF_CREATE_SKILL_RESULT_JSON line". A `partial` line (CS finished a source brief whose extraction found no export, `summary.warning` `zero-exports`) goes on to TS like a `success` one. On a `success` or `partial` line, record the `skill_package` it names (the compiled skill's folder) at once, before TS runs: `uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} --skill-path <skill_package>`.
     - **Doc-rot check:** on that same `success` or `partial` line, record the corrections CS step 5c kept: `uv run {stateScript} append-workarounds --state-file {stateFile} --skill {skill_name} --doc-rot-file "{project-root}/_bmad-output/.skf-stage/{skill_name}/doc-rot-corrections.json"`. It appends one `[doc-rot] {affected}: {candidate_category}` entry per correction to the skill's `workarounds_applied`, each once, and nothing when step 5c kept none and so wrote no file.
     - **TS** (`skf-test-skill`): first resolve the gate again, right before the test, so a directive edit made during this skill counts and the threshold never has to survive the nested runs in conversation context: `uv run {gateScript} resolve --state-file {stateFile} --skill {skill_name} [--directive-file <campaign.directive_path>]` (exit 2 HALTs as at §4), and log its `directive_notice` with `--once` as §4 does. Then run `{skill_name} --headless --threshold={threshold}` with that call's `threshold`, and `pipeline_alias` set to `campaign` in its data context (the explicit threshold wins over test-skill's per-pipeline default). TS settles its verdict, caps and 80% floor fallback itself; §5.3 reads the result.
3. **Record results:** settle the skill from its test verdict, never from an envelope's `status` (TS reports `success` for a scored FAIL too). Pipe the SKF_TEST_RESULT_JSON line TS printed (on stdout for a scored run, on stderr when it halted) to the gate script, and nothing when it printed none:

   ```
   uv run {gateScript} record --skill {skill_name} <<'SKF_RESULT'
   <the SKF_TEST_RESULT_JSON line TS printed>
   SKF_RESULT
   ```

   - `status` `completed` (verdict PASS, a threshold-fallback PASS included): `uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} --status completed --quality-score <quality_score>`, with its `quality_score`; the helper stamps `completed_at`. Whether the skill exports is decided at Export (step-10), against its gate.
   - `status` `failed` (FAIL, INCONCLUSIVE, pass-with-drift, an error envelope or no readable result), or an earlier sub-skill failed: `uv run {stateScript} set-skill --state-file {stateFile} --skill {skill_name} --status failed --halt-reason '<reason>' [--quality-score <quality_score>]`, with `--quality-score` when it has one. `<reason>` is the failure reason, also logged as an `event`, led by the sub-skill that failed (`BS`, `CS` or `TS`, such as `CS: no-result`): the record's `reason`, the failing sub-skill's `halt_reason`, else `exit <code>`, `no-result`, or `unparseable result envelope`. So `campaign status` and the report surface *why* a skill failed without the operator opening sub-skill logs. Downstream skills whose `depends_on` does NOT include the failed skill continue processing normally; those that DO depend on it are blocked at §4's dependency gate, where a headless or unattended run skips them.

### §6: Loop Completion

When all Tier A skills in `execution_order` are processed (completed, failed, or skipped), write the stage:

```
uv run {stateScript} set-stage --state-file {stateFile} --stage 4
```

## OUTPUT

Display per-skill summary: name, status, quality_score (if completed). Chain to `{nextStepFile}`.
