---
nextStepFile: 'step-06-batch.md'
stateSchemaFile: 'assets/campaign-state-schema.json'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
backupFile: '{campaignWorkspacePath}/_campaign-state.yaml.bak'
briefFile: '{campaignWorkspacePath}/campaign-brief.yaml'
depsScript: 'scripts/campaign-deps.py'
kickoffTemplate: '{kickoffTemplatePath}'
kickoffScript: 'scripts/campaign-render-kickoff.py'
gateScript: 'scripts/campaign-quality-gate.py'
validateScript: 'scripts/campaign-validate-state.py'
---

<!-- Config: communicate in {communication_language}. -->

# Skill Loop

## STEP GOAL:

Iterate skills in `dependency_graph.execution_order`, processing each Tier A skill through the full pipeline while enforcing dependency gates. Write state after each skill completes to survive context death between skills.

## RULES

- This step uses the **read-backup-modify-write** pattern.
- Validate state on load via `uv run {validateScript} --state-file {stateFile}`; HALT (exit 3) on non-zero.
- Update `campaign.current_stage` to `4`.
- Update `campaign.last_updated` to current ISO-8601 with timezone on every write.
- Write state after EACH skill completes (not just at end) — context death between skills must be survivable.
- The per-skill pipeline body (§5.2) runs inline, not in a delegated subagent: BS→CS→TS are nested skill activations, and a subagent cannot spawn further subagents, so running inline keeps the full pipeline reachable and writes each skill's state before the next begins.
- If `{headless_mode}` is true, auto-proceed through confirmation gates; at a blocked skill, headless takes §4.6's `default_action` and never forces a dependency.

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

   When `skip` is true, the directive's Skip List names the skill: mark it `"skipped"`, log "directive Skip List: {skill_name} ({skip_reason})" to the decision log, backup and write state, and continue to the next skill. Otherwise keep its `brief_skill`, the brief-skill inputs §5.2 copies. Its `unparsed` entries and `warnings` lines describe the directive, not the skill: log them to the decision log once per stage, from the first resolve call, and again only when a later call reports different ones. On exit 2, HALT with its `error`: exit code 8 (`missing-brief`) when its `code` is `BRIEF_NOT_FOUND`, `BRIEF_UNREADABLE` or `TARGET_NOT_FOUND` (the brief has no target for the skill), else exit code 2 (`invalid-input`): an override that breaks the gate, or a directive that cannot be read.
4. Run `uv run {depsScript} --check --state-file {stateFile} --skill {skill_name}`.
5. If `ready: true`, proceed to §5 for this skill.
6. If `ready: false`, present the blocked skill and each unmet dependency with its status (`unmet_status`):
   - `[S]kip`: mark skill as `"skipped"`, backup and write state, log it, continue to next skill.
   - `[F]orce`: re-run with `--force`, proceed to §5 despite unmet deps.
   - `[H]alt`: stop the campaign with exit code 13 (`dependency-blocked`); state is intact and resumable.

   **Headless:** take `default_action`. `skip` (every unmet dependency failed or was skipped, so none can complete in this run) runs `[S]kip` and logs "headless: skipped {skill_name}: {dependency} is {status}" for each unmet dependency, so the independent skills after it still run. `halt` (a dependency is still pending or active, an order the loop cannot follow) runs `[H]alt`. In execution order every dependency comes first, so `halt` is defensive: only a `--from` resume or a hand-edited state leaves a dependency pending.
7. **Deadlock detection** (defensive: Strategy rejects every order the loop cannot follow and §4.6 settles each blocked skill as the loop reaches it, so only a hand-edited state gets here): after iterating through all remaining skills and finding none ready, present the same recovery menu as §4.6, scoped to the mutually-blocked set (this is the strictly harder situation, so it must not get worse UX than a single blocked skill):
   - List the blocked skills and their unmet dependencies.
   - `[F]orce one`: choose a skill to re-run with `--force` and resume the loop from it.
   - `[S]kip one`: choose a skill to mark `"skipped"`, backup and write state, then re-evaluate readiness.
   - `[H]alt`: stop the campaign loop with exit code 7 (`dependency-deadlock`). **Default in headless mode** (headless never forces a dependency). Log the chosen action to the decision log.

### §5: Per-Skill Processing

For each ready Tier A skill:

1. **Activate** — set `status` to `"active"`, set `started_at` to current ISO-8601 with timezone. Backup and write state.
2. **Execute pipeline:**
   - **Pre-apply** — apply known workarounds before generation by running the shared pre-apply helper against the skill's working directory:
     ```
     uv run {project-root}/_bmad/skf/shared/scripts/skf-preapply.py --target-dir <skill-working-dir> --log-dir {campaignWorkspacePath}
     ```
     (During development the helper lives at `src/shared/scripts/skf-preapply.py`.) Parse `applied[]` from the JSON output and capture the list of applied workarounds. Pre-apply is best-effort: if the helper is missing or exits non-zero, log a warning and proceed — it is not a gate.
   - **Kickoff emit:** render the whole kickoff message with the kickoff script, which fills every placeholder of the template. The customization resolver pipes the persistent facts into it:
     ```
     uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow.persistent_facts | uv run {kickoffScript} --state-file {stateFile} --brief-file {briefFile} --skill {skill_name} --template {kickoffTemplate} --workarounds '<JSON list of applied workarounds from pre-apply>' --facts-json - --project-root {project-root} [--directive-file <campaign.directive_path>]
     ```
     - `--facts-json -` takes `workflow.persistent_facts` from the resolver unchanged. When the resolver is missing or fails, drop the pipe and pass the `persistent_facts` list of `{skill-root}/customize.toml` as written: `--facts-json '<JSON list>'`.
     - Write each `'` inside a single-quoted JSON value as the JSON escape `\u0027`.
     - `--directive-file` is passed when state sets `campaign.directive_path`.

     Present the script's output unchanged as the context for the skill's pipeline run, and fill nothing in by hand. An exit 2 with no JSON on stderr is a usage error from a mangled call, not invalid input: fix the quoting and run it again. An exit 2 with JSON names its `code`: on `BAD_WORKAROUNDS` or `BAD_FACTS` this call's input is wrong, so correct it and run the call again; on `BRIEF_NOT_FOUND` or `BRIEF_UNREADABLE`, HALT (exit code 8, `missing-brief`); on any other code, HALT (exit code 2, `invalid-input`) with its `error`. Correct a call once only: when the corrected call fails too, HALT (exit code 2, `invalid-input`).
   - **BS → CS → TS**: the forge pipeline for a named skill, the chain the forger's `forge` alias runs. Run each sub-skill with `--headless`, so no nested gate waits and each prints its result envelope. A sub-skill that fails ends the pipeline, and the skill fails (§5.3) with its `halt_reason`. Campaign runs no analyze-source pass: brief-skill scopes the named skill itself, while analyze-source names its briefs from the repository, so brief-skill would overwrite or never read them.
     - **BS** (`skf-brief-skill`): `--headless --force` with each non-null field of §4's `brief_skill` as the input of that name (`target_repo`, `skill_name`, `target_version`, `language_hint`, `scope_hint`); copy them, never read them out of the kickoff. `target_version` is the skill's pin: Setup accepts only an X.Y.Z version as a Tier A pin, and brief-skill refuses any other shape with `input-invalid`, so a pin never silently drops out of the build. `--force` replaces a brief an earlier attempt wrote under this name. Set `skills[current].brief_path` to the `brief_path` of its SKF_BRIEF_RESULT_JSON, so the field the schema declares is populated and available for resume and reporting. An envelope with `status` `error`, or none, fails the skill.
     - **CS** (`skf-create-skill`): `--headless` with that `brief_path`. CS prints an SKF_CREATE_SKILL_RESULT_JSON line (on stderr) only when it halts; that line fails the skill with its `summary.halt_reason`. On success, keep the `{skill_package}` its report names (the compiled skill's folder): §5.3 records it.
     - **TS** (`skf-test-skill`): first resolve the gate again, right before the test, so a directive edit made during this skill counts and the threshold never has to survive the nested runs in conversation context: `uv run {gateScript} resolve --state-file {stateFile} --skill {skill_name} [--directive-file <campaign.directive_path>]` (exit 2 HALTs as at §4). Then run `{skill_name} --headless --threshold={threshold}` with that call's `threshold`, and `pipeline_alias` set to `campaign` in its data context (the explicit threshold wins over test-skill's per-pipeline default). TS settles its verdict, caps and 80% floor fallback itself; §5.3 reads the result.
   - **Doc-rot check:** **record** what CS step 5c already produced; do not re-derive it. Because the pipeline body runs inline (see the RULES note on inline execution), that step's context is directly readable here. Its `correction_matches` holds only the corrections step 5c's judgment pass kept and wrote as `## CORRECTION` blocks, each with `source`, `pattern`, `candidate_category`, `context_line` and `affected`; the candidates the pass rejected are not corrections, so they are never recorded. Append one entry per `correction_matches` record to the skill's `workarounds_applied` array, written as `[doc-rot] {affected}: {candidate_category}`, so they survive the state write. When step 5c took its skip branch (`doc_rot_triggered: false`, `corrections_added: 0`), there is nothing to record: append nothing and move on.

     **Do not hand-grep the feeder artifacts here, and do not re-run the scan.** `skf-create-skill/references/step-doc-rot.md` §2 requires the scan to run in its helper precisely so identical feeders yield identical matches; a second pass in this loop is free to disagree with the corrections CS actually wrote. It would also be self-contaminating: step 5c has already written `## CORRECTION` blocks into the compiled SKILL.md, and the helper's exclusion windows cover only that file's frontmatter and its Migration & Deprecation Warnings section — so re-scanning it would re-match the blocks 5c itself authored and record them as fresh findings.
3. **Record results:** settle the skill from its test verdict, never from an envelope's `status` (TS reports `success` for a scored FAIL too). Pipe the SKF_TEST_RESULT_JSON line TS printed (on stdout for a scored run, on stderr when it halted) to the gate script, and nothing when it printed none:

   ```
   uv run {gateScript} record --skill {skill_name} <<'SKF_RESULT'
   <the SKF_TEST_RESULT_JSON line TS printed>
   SKF_RESULT
   ```

   - `status` `completed` (verdict PASS, a threshold-fallback PASS included): set `status` to `"completed"`, set `completed_at` to current ISO-8601 with timezone, record `quality_score` from its `quality_score` and `skill_path` from the `{skill_package}` CS named. Backup and write state. Whether the skill exports is decided at Export (step-10), against its gate.
   - `status` `failed` (FAIL, INCONCLUSIVE, pass-with-drift, an error envelope or no readable result), or an earlier sub-skill failed: set `status` to `"failed"`, and record its `quality_score` when it has one. Log the failure reason (the record's `reason`, the failing sub-skill's `halt_reason`/exit code, or "unparseable result envelope") to the decision log so `campaign status` and the report surface *why* a skill failed without the operator opening sub-skill logs. Backup and write state. Downstream skills whose `depends_on` does NOT include the failed skill continue processing normally; those that DO depend on it are blocked at §4's dependency gate, where headless skips them.

### §6: Loop Completion

When all Tier A skills in `execution_order` are processed (completed, failed, or skipped):

1. Set `campaign.current_stage` to `4`.
2. Set `campaign.last_updated` to current ISO-8601 with timezone.
3. Backup and write state.

## OUTPUT

Display per-skill summary: name, status, quality_score (if completed). Chain to `{nextStepFile}`.
